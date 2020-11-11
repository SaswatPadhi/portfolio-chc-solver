from pathlib import Path
from subprocess import PIPE, run
from tempfile import mkstemp as make_tempfile


ENGINE = 'freqhorn'
FORMAT = 'smt'


logger = None


def setup(args):
    global logger

    logger = args.logging.getLogger(f'({ENGINE})')
    logger.setLevel(args.logging.getLevelName(args.log_level))


def preprocess(args):
    global logger

    if args.format != FORMAT:
        _, tfile_path = make_tempfile(suffix=f'.freqhorn.from-{args.format}.{FORMAT}')
        
        translator = args.translators_path.joinpath(f'{args.format}-to-{FORMAT}.py')
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

    _, tfile_path = make_tempfile(suffix=f'.freqhorn.smt')

    with open(tfile_path, 'w') as tfile_handle:
        with open(args.input_file, 'r') as input_handle:
            tfile_handle.writelines(line for line in input_handle.readlines()
                                         if line.strip() != "(get-model)")
    args.input_file = tfile_path

    return args


def solve(args):
    global logger

    solver_path = Path(__file__).resolve().parent.joinpath('freqhorn')

    logger.debug(f'Exec: {solver_path} {args.input_file}')
    result = run([solver_path, args.input_file], stdout=PIPE, stderr=PIPE)

    try:
        result.check_returncode()
        output = result.stdout.decode('utf-8').strip()
        if 'Unsupported' in output or 'unsupported' in output:
            raise AssertionError()
        return '\n'.join(output.splitlines()[1:])
    except Exception as _:
        error = result.stderr.decode('utf-8').strip()
        if error:
            error = f'\nSTDERR:\n{error}'
        output = result.stdout.decode('utf-8').strip()
        if output:
            output = f'\nSTDOUT:\n{output}'
        logger.error(f'Solver terminated with an error!{error}{output}')
        return None
