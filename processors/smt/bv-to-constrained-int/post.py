#!/usr/bin/env python3

import pyparsing as pp
import sys

from argparse import ArgumentDefaultsHelpFormatter, ArgumentParser, FileType


pp.ParserElement.enablePackrat()


def serialize(statement):
    if type(statement) is not list:
        return statement
    return f'({" ".join(serialize(e) for e in statement)})'

def main(args):
    i_expr = pp.QuotedString(quoteChar='"') | pp.QuotedString(quoteChar='|', unquoteResults=False)
    s_expr = pp.nestedExpr(opener='(', closer=')', ignoreExpr=i_expr)
    s_expr.ignore(';' + pp.restOfLine)

    parser = pp.ZeroOrMore(s_expr)
    ast = parser.parseFile(args.input_file, parseAll=True).asList()

    sys.stdout.writelines(serialize(statement) + '\n' for statement in ast)

if __name__ == '__main__':
    parser = ArgumentParser(formatter_class=ArgumentDefaultsHelpFormatter)

    parser.add_argument(
        'input_file', type=FileType('r'),
        help='Path to an input file (or stdin if "-")')

    main(parser.parse_args())
