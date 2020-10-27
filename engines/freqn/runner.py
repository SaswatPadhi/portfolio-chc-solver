from pathlib import Path
from subprocess import PIPE, run
from tempfile import mkstemp as make_tempfile


ENGINE = 'freqn'


logger = None


def setup(args):
    global logger

    logger = args.logging.getLogger(f'({ENGINE})')
    logger.setLevel(args.logging.getLevelName(args.log_level))


def preprocess(args):
    global logger

    if args.format != 'smt':
        _, tfile_path = make_tempfile(suffix=f'.freqn.smt')
        
        translator = args.translators_path.joinpath(f'{args.format}-to-sygus.py')
        if not translator.is_file():
            logger.error(f'Could not locate translator "{translator}"!')
            raise FileNotFoundError(translator)

        logger.info(f'Translating input from {args.format} -> {tfile_path} ...')
        logger.debug(f'Exec: python3 {translator} {args.input_file}')

        result = run(['python3', translator, args.input_file], stdout=PIPE, stderr=PIPE)
        result.check_returncode()

        with open(tfile_path, 'w') as tfile_handle:
            tfile_handle.writelines(result.stdout.decode('utf-8'))
        args.input_file = tfile_path

    return args


def solve(args):
    global logger

    solver_path = Path(__file__).resolve().parent.joinpath('freqn')

    logger.debug(f'Exec: {solver_path} {args.input_file}')
    result = run([solver_path, args.input_file], stdout=PIPE, stderr=PIPE)

    try:
        result.check_returncode()
        output = result.stdout.decode('utf-8').strip()
        if 'Unsupported' in output or 'unsupported' in output:
            raise AssertionError()
        return output
    except Exception as _:
        error = result.stderr.decode('utf-8').strip()
        if error:
            error = f'\nSTDERR:\n{error}'
        output = result.stdout.decode('utf-8').strip()
        if output:
            output = f'\nSTDOUT:\n{output}'
        logger.error(f'Solver terminated with an error!{error}{output}')
        return None
