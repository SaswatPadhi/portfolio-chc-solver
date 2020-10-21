from pathlib import Path
from subprocess import PIPE, run
from tempfile import mkstemp as make_tempfile


ENGINE = 'z3-spacer'


logger = None


def setup(args):
    global logger

    logger = args.logging.getLogger(f'({ENGINE})')
    logger.setLevel(args.logging.getLevelName(args.log_level))


def preprocess(args):
    global logger

    from mmap import ACCESS_READ, mmap
    from shutil import copyfile

    if args.format != 'smt':
        _, tfile_path = make_tempfile(suffix=f'.z3-spacer.smt')
        
        translator = args.translators_path.joinpath(f'{args.format}-to-smt.py')
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
    else:
        with open(args.input_file, 'rb', 0) as file:
            with mmap(file.fileno(), 0, access=ACCESS_READ) as s:
                if s.find(b'(get-model)') != -1:
                    return args

        _, tfile_path = make_tempfile(suffix=f'.z3-spacer.smt')
        copyfile(args.input_file, tfile_path)

        with open(tfile_path, 'a') as tfile_handle:
            tfile_handle.write('\n(get-model)\n')
        args.input_file = tfile_path
        
    return args


def solve(args):
    global logger

    solver_path = Path(__file__).resolve().parent.joinpath('z3')

    logger.debug(f'Exec: {solver_path} {args.input_file}')
    result = run([solver_path, args.input_file], stdout=PIPE, stderr=PIPE)
    
    try:
        result.check_returncode()
        return '\n'.join(result.stdout.decode('utf-8').strip().splitlines()[1:])
    except Exception as _:
        error = result.stderr.decode('utf-8').strip()
        if error:
            error = f'\nSTDERR:\n{error}'
        output = result.stdout.decode('utf-8').strip()
        if output:
            output = f'\nSTDOUT:\n{output}'
        logger.error(f'Solver terminated with an error!{error}{output}')
        return None
