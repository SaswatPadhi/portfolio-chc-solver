from pathlib import Path
from subprocess import PIPE, run
from tempfile import mkstemp as make_tempfile


ENGINE = 'z3-spacer'


logger = None


def setup(args, logging):
    global logger

    logger = logging.getLogger(f'({ENGINE})')
    logger.setLevel(logging.getLevelName(args.log_level))


def preprocess(args):
    global logger

    from mmap import ACCESS_READ, mmap

    with open(args.input_file, 'rb', 0) as file, mmap(file.fileno(), 0, access=ACCESS_READ) as s:
        if s.find(b'(get-model)') == -1:
            with open(args.input_file, 'a') as wfile:
                wfile.write('\n(get-model)\n')

    if args.mode == 'smt':
        return args

    _, tfile_path = make_tempfile(suffix=f'.z3-spacer.smt')
    
    translator = args.translators_dir.joinpath('from-sygus.py')
    if not translator.is_file():
        logger.error(f'Could not locate translator "{translator}"')
        raise FileNotFoundError(translator)

    logger.info(f'Translating input from {args.mode} -> {tfile_path} ...')
    logger.debug(f'Exec: python3 {translator} {args.input_file}')

    result = run(['python3', translator, args.input_file], stdout=PIPE, stderr=PIPE)
    result.check_returncode()

    with open(tfile_path, 'w') as tfile_handle:
        tfile_handle.writelines(result.stdout.decode('utf-8'))
    args.input_file = tfile_path

    return args


def solve(args):
    global logger

    self_path = Path(__file__).resolve().parent
    solver_path = self_path.joinpath('z3')

    logger.debug(f'Exec: {solver_path} {args.input_file}')
    result = run([solver_path, args.input_file], stdout=PIPE, stderr=PIPE)
    result.check_returncode()

    return result.stdout.decode('utf-8').splitlines()[1:]
