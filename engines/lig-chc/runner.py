from pathlib import Path
from subprocess import PIPE, run
from tempfile import mkstemp as make_tempfile


ENGINE = 'lig-chc'


logger = None


def setup(args, logging):
    global logger

    logger = logging.getLogger(f'({ENGINE})')
    logger.setLevel(logging.getLevelName(args.log_level))


def preprocess(args):
    global logger

    if args.mode == 'sygus':
        return args

    _, tfile_path = make_tempfile(suffix=f'.lig-chc.sygus')
    
    translator = args.translators_dir.joinpath('to-sygus.py')
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
    solver_path = self_path.joinpath('lig-chc.sh')

    logger.debug(f'Exec: {solver_path} {args.input_file}')
    result = run([solver_path, args.input_file], stdout=PIPE, stderr=PIPE)
    result.check_returncode()

    return result.stdout.decode('utf-8')
