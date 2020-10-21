#!/usr/bin/env python3

import logging

from importlib import import_module
from multiprocessing import cpu_count, Process, Queue
from pathlib import Path
from sys import exit
from tempfile import mkstemp as make_tempfile


SELF_PATH = Path(__file__).resolve().parent


def run(engine, args, queue):
    logger = logging.getLogger(f'w:{engine}')
    logger.setLevel(logging.getLevelName(args.log_level))

    engine_path = SELF_PATH.joinpath('engines', engine)
    if not engine_path.is_dir():
        logger.critical(f'Failed to locate "{engine}" engine at "{engines_path}"!')
        queue.put((engine, 'FAIL'))
        return

    engine_path = engine_path.joinpath('runner.py')
    if not engine_path.is_file():
        logger.error(f'Failed to locate "{engine}" runner at "{engines_path}"!')
        queue.put((engine, 'FAIL'))
        return

    engine_runner = import_module(f'engines.{engine}.runner')
    engine_runner.setup(args, logging)

    if hasattr(engine_runner, 'preprocess'):
        try:
            logger.debug(f'Preprocessing "{args.input_file}" for {engine} ...')
            args = engine_runner.preprocess(args)
        except Exception as e:
            logger.error(f'Exception encountered during preprocessing:')
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
    except Exception as e:
        logger.error(f'Exception encountered during solving:')
        logger.exception(e)
        queue.put((engine, 'FAIL'))


def main(args, engines):
    logger = logging.getLogger('solver')
    logger.setLevel(logging.getLevelName(args.log_level))

    logger.debug(f'Started portfolio solver with mode = "{args.mode}", log level = "{args.log_level}".')

    _, tfile_path = make_tempfile(suffix=f'.{args.mode}')
    logger.info(f'Cloning input to file: {tfile_path}.')
    with open(tfile_path, 'w') as tfile_handle:
        tfile_handle.writelines(args.input_file.readlines())
    args.input_file = Path(tfile_path).resolve()
    
    if args.disable_engine:
        for engine in args.disable_engine:
            if engine in engines:
                logger.info(f'Disabled CHC solver engine: {engine}.')
            else:
                logger.warning(f'Cannot disable unknown CHC solver engine: {engine}.')
        engines = [engine for engine in engines if engine not in args.disable_engine]
    logger.info(f'Enabled CHC solver engines: {engines}.')
    if cpu_count() <= len(engines):
        logger.warning(f'Starting {len(engines)} worker(s) on {cpu_count()} CPU(s).')
    elif len(engines) > 0:
        logger.info(f'Starting {len(engines)} worker(s) on {cpu_count()} CPU(s).')
    else:
        logger.critical(f'No CHC solver engines are enabled!')
        exit(1)

    queue = Queue()
    workers = []
    for engine in engines:
        worker = Process(target=run, args=(engine, args, queue))
        workers.append(worker)
        worker.start()

    waiting = len(workers)
    while waiting > 0:
        (engine, result) = queue.get()
        if result != 'FAIL':
            logger.info(f'First solution received from {engine}')
            print(result, end='')
            break
        else:
            logger.warning(f'CHC solver engine {engine} failed.')
            waiting -= 1

    if waiting < 1:
        logger.error(f'No CHC solver engines were able to provide a solution!')

    logger.debug(f'Terminating remaining CHC solver engines ...')
    for worker in workers:
        worker.terminate()

    logger.debug(f'Shutting down portfolio solver.')
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
        level=logging.INFO)
    logger = logging.getLogger('boot')

    logger.info(f'Booting portfolio solver at "{SELF_PATH}".')
    
    engines_path = SELF_PATH.joinpath('engines')
    if not engines_path.is_dir():
        logger.critical(f'No CHC solver engines found at "{engines_path}"!')
        exit(1)

    engines = [engine.name for engine in engines_path.glob('*')
               if engine.is_dir() and engine.name != '__pycache__' ]
    logger.info(f'Detected CHC solver engines: {engines}.')
    
    parser = ArgumentParser(formatter_class=ArgumentDefaultsHelpFormatter)
    parser.add_argument('-d', '--disable-engine',
                        action='append', choices=engines,
                        help='Disable a CHC solver engine')
    parser.add_argument('-l', '--log-level',
                        type=str.upper, default='INFO',
                        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
                        help='Set the logging level (default: %(default)s)')
    parser.add_argument('-m', '--mode',
                        type=str.lower, default='smt', choices=['smt','sygus'],
                        help='Select the input format')
    parser.add_argument('-t', '--translators-dir',
                        type=dir_path, default=f'{SELF_PATH.joinpath("translators")}',
                        help='Path to the directory containing SMT <-> SyGuS translators.')
    parser.add_argument('input_file',
                        type=FileType('r'),
                        help='Path to an input file (or <stdin> if "-")')

    main(parser.parse_args(), engines)
