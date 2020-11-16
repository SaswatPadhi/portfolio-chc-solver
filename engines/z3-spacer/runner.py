import pyparsing as pp

from pathlib import Path
from subprocess import PIPE, run
from tempfile import mkstemp as make_tempfile


ENGINE = 'z3-spacer'
FORMAT = 'smt'


logger = None
parser = None
tracked_symbols = dict()

pp.ParserElement.enablePackrat()


def setup(args):
    global logger, parser

    logger = args.logging.getLogger(f'({ENGINE})')
    logger.setLevel(args.logging.getLevelName(args.log_level))

    i_expr = pp.QuotedString(quoteChar='"') | pp.QuotedString(quoteChar='|', unquoteResults=False)
    s_expr = pp.nestedExpr(opener='(', closer=')', ignoreExpr=i_expr)
    s_expr.ignore(';' + pp.restOfLine)

    parser = pp.ZeroOrMore(s_expr)

def quote_name(name):
    pre, post = '', ''
    if not name.startswith('|'):
        pre = '|'
    if not name.endswith('|'):
        post = '|'
    return f'{pre}{name}{post}'

def preprocess(args):
    global logger, parser, tracked_symbols

    from mmap import ACCESS_READ, mmap

    if args.format != FORMAT:
        _, tfile_path = make_tempfile(suffix=f'.z3-spacer.from-{args.format}.{FORMAT}')
        
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

    get_model_needed = True
    with open(args.input_file, 'rb', 0) as file:
        with mmap(file.fileno(), 0, access=ACCESS_READ) as s:
            if s.find(b'(get-model)') != -1:
                get_model_needed = False

    if get_model_needed:
        from shutil import copyfile

        _, tfile_path = make_tempfile(suffix=f'.z3-spacer.smt')
        copyfile(args.input_file, tfile_path)

        with open(tfile_path, 'a') as tfile_handle:
            tfile_handle.write('\n(get-model)\n')
        args.input_file = tfile_path

    tracked_symbols = {
        quote_name(stmt[1]) : stmt[2]
        for stmt in parser.parseFile(args.input_file, parseAll=True).asList()
        if stmt[0] == 'declare-fun'
    }
    logger.debug(tracked_symbols)

    return args

def serialize(statement):
    if type(statement) is not list:
        return statement
    return f'({" ".join(serialize(e) for e in statement)})'

def substitute(expr, replacements):
    if type(expr) is not list:
        return

def shrink(output):
    global logger, parser, tracked_symbols

    result = []
    for stmt in parser.parseString(output, parseAll=True).asList()[0][1:]:
        if stmt[0] == 'define-fun':
            stmt[1] = quote_name(stmt[1])
            args = tracked_symbols.get(stmt[1], None)
            if args is not None:
                assert len(stmt[2]) == len(tracked_symbols[stmt[1]])
                substitute(stmt, zip(stmt[2], tracked_symbols[stmt[1]]))
                result.append(stmt)

    return '\n'.join(serialize(stmt) for stmt in result)

def solve(args):
    global logger

    solver_path = Path(__file__).resolve().parent.joinpath('z3')

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

        return shrink(output[output.find('\n')+1:])
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
