#!/usr/bin/env python3

import logging

from copy import copy
from importlib import import_module
from multiprocessing import cpu_count, Process, Queue
from pathlib import Path
from subprocess import PIPE, run
from sys import exit
from tempfile import mkstemp as make_tempfile


SELF_PATH = Path(__file__).resolve().parent


def run_engine_process(engine, args, queue):
    logger = args.logging.getLogger(f'e:{engine}')
    logger.setLevel(args.logging.getLevelName(args.log_level))

    engine_path = args.engines_path.joinpath(engine)
    if not engine_path.is_dir():
        logger.critical(f'Failed to locate "{engine}" engine at "{engine_path}"!')
        queue.put((engine, 'FAIL'))
        return

    engine_path = engine_path.joinpath('runner.py')
    if not engine_path.is_file():
        logger.error(f'Failed to locate "{engine}" runner at "{engine_path}"!')
        queue.put((engine, 'FAIL'))
        return

    engine_runner = import_module(f'engines.{engine}.runner')
    try:
        engine_runner.setup(args)
    except Exception as e:
        logger.error(f'Engine "{engine}" could not be setup!')
        logger.exception(e)
        queue.put((engine, 'FAIL'))
        return

    if hasattr(engine_runner, 'preprocess'):
        try:
            logger.debug(f'Preprocessing "{args.input_file}" for "{engine}" engine ...')
            args = engine_runner.preprocess(args)
            for processor in args.process.get(engine, []):
                processor_path = args.processors_path.joinpath(engine_runner.FORMAT).joinpath(processor).joinpath('pre.py')
                if not processor_path.is_file():
                    raise FileNotFoundError(processor_path)

                _, tfile_path = make_tempfile(suffix=f'.{engine}.{processor}.pre.{engine_runner.FORMAT}')
                logger.debug(f'Additional processor: python3 {processor_path} {args.input_file}')
                result = run(['python3', processor_path, args.input_file], stdout=PIPE, stderr=PIPE)
                result.check_returncode()

                with open(tfile_path, 'w') as tfile_handle:
                    tfile_handle.writelines(result.stdout.decode('utf-8'))
                args.input_file = tfile_path

            logger.info(f'Input preprocessing is complete.')
        except Exception as e:
            logger.error(f'Exception encountered during input preprocessing:')
            logger.exception(e)
            queue.put((engine, 'FAIL'))
            return

    logger.debug(f'Starting solver: {engine}("{args.input_file}").')
    try:
        result = engine_runner.solve(args)
        if not result:
            queue.put((engine, 'FAIL'))
        else:
            queue.put((engine, result))
            logger.debug(f'A solution was found:\n{result}')
    except Exception as e:
        logger.error(f'Exception encountered during solving:')
        logger.exception(e)
        queue.put((engine, 'FAIL'))


def main(args):
    logger = args.logging.getLogger('portfolio')
    logger.setLevel(args.logging.getLevelName(args.log_level))

    logger.debug(f'Started portfolio solver with format = "{args.format}", log level = "{args.log_level}".')

    _, tfile_path = make_tempfile(suffix=f'.{args.format}')
    logger.debug(f'Cloning input from "{args.input_file.name}" to file: {tfile_path}.')
    with open(tfile_path, 'w') as tfile_handle:
        tfile_handle.writelines(args.input_file.readlines())
    args.input_file = Path(tfile_path).resolve()
    
    engines = args.engines
    if args.disable_engine:
        for engine in args.disable_engine:
            if engine in args.engines:
                logger.debug(f'Disabled "{engine}" engine.')
            else:
                logger.warning(f'Cannot disable unknown engine: "{engine}".')
        engines = [engine for engine in engines if engine not in args.disable_engine]
    elif args.enable_engine:
        engines = []
        for engine in args.enable_engine:
            if engine in args.engines:
                logger.debug(f'Enabled "{engine}" engine.')
            else:
                logger.warning(f'Cannot enable unknown engine: "{engine}".')
            if not engine in engines:
                engines.append(engine)

    processors = dict()
    if args.process:
        for p in args.process:
            split_p = p.split(':')
            if len(split_p) != 2:
                logger.warning(f'Ignoring invalid process flag: {p}!')
                continue
            if split_p[0] not in engines:
                logger.warning(f'Ignoring process flag "{p}" for disabled engine "{split_p[0]}"')
            if split_p[0] not in processors:
                processors[split_p[0]] = []
            if split_p[1] not in processors[split_p[0]]:
                processors[split_p[0]].append(split_p[1])
                logger.debug(f'Registered processor "{split_p[1]}" for "{split_p[0]}" engine.')
    args.process = processors

    logger.debug(f'Active engines: {", ".join([f"{e}{processors.get(e,[])}" for e in engines])}.')

    if cpu_count() <= len(engines):
        logger.warning(f'Starting {len(engines)} engine(s); have {cpu_count()} CPU(s).')
    elif len(engines) > 0:
        logger.info(f'Starting {len(engines)} engine(s); {cpu_count()} CPU(s).')
    else:
        logger.critical(f'No engines are enabled! Quitting portfolio solver.')
        exit(1)

    queue = Queue()
    workers = []
    for engine in engines:
        args_copy = copy(args)
        worker = Process(target=run_engine_process, args=(engine, args_copy, queue))
        workers.append(worker)
        worker.start()

    waiting = len(workers)
    while waiting > 0:
        (engine, result) = queue.get()
        if result != 'FAIL':
            logger.info(f'Received a solution from engine "{engine}".')
            print(result)
            break
        else:
            logger.warning(f'Engine "{engine}" failed with an exception!')
            waiting -= 1

    if waiting < 1:
        logger.critical(f'No engines were able to find a solution!')
        exit(1)

    logger.debug(f'Terminating remaining engines ...')
    for worker in workers:
        worker.terminate()

    logger.debug(f'Quitting portfolio solver.')
    exit(0)


if __name__ == '__main__':
    def dir_path(string):
        path = Path(string).resolve()
        if path.is_dir():
            return path
        else:
            raise NotADirectoryError(string)

    from argparse import ArgumentDefaultsHelpFormatter, ArgumentParser, FileType

    logging.basicConfig(
        format='%(asctime)s [%(levelname)8s] %(name)12s - %(message)s',
        level=logging.CRITICAL)
    logger = logging.getLogger('boot')

    logger.debug(f'Booting portfolio solver at "{SELF_PATH}".')
    
    engines_path = SELF_PATH.joinpath('engines')
    if not engines_path.is_dir():
        logger.critical(f'Engines directory "{engines_path}" does not exist!')
        exit(1)

    engines = [e.name for e in engines_path.glob('*')
               if e.is_dir() and e.name != '__pycache__' ]
    logger.debug(f'Detected engines: {engines}.')
    
    processors_path = SELF_PATH.joinpath('processors')
    if not processors_path.is_dir():
        logger.critical(f'Processors directory "{processors_path}" does not exist!')
        exit(1)

    processors = [f'{p.name} ({p.parent.name})'
                  for p in processors_path.glob('*/*')
                  if p.is_dir() and p.name != '__pycache__' ]
    logger.debug(f'Detected processors: {processors}.')
    
    translators_path = SELF_PATH.joinpath('translators')
    if not translators_path.is_dir():
        logger.warning(f'Translators directory "{translators_path}" does not exist!')

    translators = [t.name[:-3] for t in translators_path.glob('*.py')
                   if t.is_file() and t.name != '__init__.py' ]
    logger.debug(f'Detected translators: {translators}.')
    
    parser = ArgumentParser(
        formatter_class=ArgumentDefaultsHelpFormatter,
        epilog=f'Available processors: {", ".join(processors)}')
    parser.add_argument('-f', '--format',
                        type=str.lower, default='smt', choices=['smt','sygus'],
                        help='The input file format (default: %(default)s)')
    parser.add_argument('-l', '--log-level',
                        type=str.upper, default='INFO',
                        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
                        help='Set the logging level (default: %(default)s)')

    enable_disable_group = parser.add_mutually_exclusive_group()
    enable_disable_group.add_argument('-e', '--enable-engine',
                                      action='append', choices=engines,
                                      help='Enable a CHC solver engine')
    enable_disable_group.add_argument('-d', '--disable-engine',
                                      action='append', choices=engines,
                                      help='Disable a CHC solver engine')

    parser.add_argument('-p', '--process',
                        action='append',
                        help='Tool-specific input processing: <tool>:<processor>')

    parser.add_argument('input_file',
                        type=FileType('r'),
                        help='Path to an input file (or <stdin> if "-")')

    args = parser.parse_args()

    args.logging = logging

    args.engines_path = engines_path
    args.engines = engines

    args.processors_path = processors_path
    args.processors = processors

    args.translators_path = translators_path
    args.translators = translators

    main(args)
