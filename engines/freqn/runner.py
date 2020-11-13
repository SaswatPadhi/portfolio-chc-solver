from pathlib import Path
from subprocess import PIPE, run
from tempfile import mkstemp as make_tempfile


ENGINE = 'freqn'
FORMAT = 'smt'


logger = None


def setup(args):
    global logger

    logger = args.logging.getLogger(f'({ENGINE})')
    logger.setLevel(args.logging.getLevelName(args.log_level))


def preprocess(args):
    global logger

    from mmap import ACCESS_READ, mmap

    if args.format != FORMAT:
        _, tfile_path = make_tempfile(suffix=f'.freqn.from-{args.format}.{FORMAT}')
        
        translator = args.translators_path.joinpath(f'{args.format}-to-{FORMAT}.py')
        if not translator.is_file():
            logger.error(f'Could not locate translator "{translator}"!')
            raise FileNotFoundError(translator)

        logger.debug(f'Translating from {args.format} -> {tfile_path}: python3 {translator} {args.input_file}')
        result = run(['python3', translator, args.input_file], stdout=PIPE, stderr=PIPE)
        result.check_returncode()

        with open(tfile_path, 'w') as tfile_handle:
            tfile_handle.writelines(result.stdout.decode('utf-8'))
        args.input_file = tfile_path

    get_model_removal_needed = False
    with open(args.input_file, 'rb', 0) as file:
        with mmap(file.fileno(), 0, access=ACCESS_READ) as s:
            if s.find(b'(get-model)') != -1:
                get_model_removal_needed = True

    if get_model_removal_needed:
        _, tfile_path = make_tempfile(suffix=f'.freqn.smt')

        with open(tfile_path, 'w') as tfile_handle:
            with open(args.input_file, 'r') as input_handle:
                tfile_handle.writelines(line for line in input_handle.readlines()
                                             if line.strip() != "(get-model)")
        args.input_file = tfile_path

    return args


def solve(args):
    global logger

    solver_path = Path(__file__).resolve().parent.joinpath('freqn')

    logger.debug(f'Exec: {solver_path} {args.input_file}')
    result = run([solver_path, args.input_file], stdout=PIPE, stderr=PIPE)

    try:
        result.check_returncode()

        log_error, error = '', result.stderr.decode('utf-8').strip()
        if error:
            log_error = f'\nSTDERR:\n{error}'
        
        log_output, output = '', result.stdout.decode('utf-8').strip()
        if output:
            log_output = f'\nSTDOUT:\n{output}'
        logger.debug(f'Raw solver output:{log_error}{log_output}')

        if 'Unsupported' in output or 'unsupported' in output:
            raise AssertionError()

        return '\n'.join(output.splitlines()[1:])
    except Exception as e:
        log_error, error = '', result.stderr.decode('utf-8').strip()
        if error:
            log_error = f'\nSTDERR:\n{error}'
        
        log_output, output = '', result.stdout.decode('utf-8').strip()
        if output:
            log_output = f'\nSTDOUT:\n{output}'

        logger.error(f'Solver terminated with an error!{error}{output}')
        logger.exception(e)
        return None
