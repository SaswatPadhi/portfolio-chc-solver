#!/usr/bin/env python3

import pyparsing as pp
import re
import sys

from argparse import ArgumentDefaultsHelpFormatter, ArgumentParser, FileType


bv_widths = set()
def extract_bv_widhts(ast):
    if type(ast) is not list:
        return

    if ast[0] == '_' and ast[1] == 'BitVec':
        bv_widths.add(int(ast[2]))
        return

    for e in ast:
        extract_bv_widhts(e)

def generate_bv_functions(width):
    return f"""
(define-fun SIGNED_INT_MIN_{width} () Int (- 0 {2 ** (width - 1)}))
(define-fun SIGNED_INT_MAX_{width} () Int {(2 ** (width - 1)) - 1})
(define-fun UNSIGNED_INT_MAX_{width} () Int {(2 ** width) - 1})

(define-fun is_int_{width} ((x Int)) Bool
  (and (<= 0 x) (<= x UNSIGNED_INT_MAX_{width})))

(define-fun lbound_signed_int_{width} ((x Int)) Bool
  (and (<= 0 x) (< x {2 ** width})))

(define-fun ubound_signed_int_{width} ((x Int)) Bool
  (and (<= 0 x) (< x {2 ** width})))
    """

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

    extract_bv_widhts(ast)
    if len(bv_widths) < 1:
        sys.stdout.writelines(serialize(statement) + '\n' for statement in ast)
        return

    s
    sys.stdout.writelines(serialize(statement) + '\n' for statement in ast)

if __name__ == '__main__':
    parser = ArgumentParser(formatter_class=ArgumentDefaultsHelpFormatter)

    parser.add_argument(
        'input_file', type=FileType('r'),
        help='Path to an input file (or stdin if "-")')

    main(parser.parse_args())
