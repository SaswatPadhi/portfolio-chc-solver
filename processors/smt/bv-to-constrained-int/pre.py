#!/usr/bin/env python3

import pyparsing as pp
import sys

from argparse import ArgumentDefaultsHelpFormatter, ArgumentParser, FileType


pp.ParserElement.enablePackrat()


def serialize(statement):
    if type(statement) is not list:
        return statement
    return f'({" ".join(serialize(e) for e in statement)})'

def extract_bv_widths(ast):
    bv_widths = set()
    def helper(ast):
        if type(ast) is not list:
            return
        if ast[0] == '_' and ast[1] == 'BitVec':
            bv_widths.add(int(ast[2]))
        for e in ast:
            helper(e)

    helper(ast)
    return bv_widths

def generate_bv_functions(width):
    return f"""
(define-fun SIGNED_INT_MAX_{width} () Int {(2 ** (width - 1)) - 1})
(define-fun UNSIGNED_INT_MAX_{width} () Int {(2 ** width) - 1})

(define-fun is_int_{width} ((x Int)) Bool
  (and (<= 0 x) (<= x UNSIGNED_INT_MAX_{width})))

; assumes (>= x (- 0 UNSIGNED_INT_MAX_{width}))
(define-fun lbound_int_{width} ((x Int)) Int
  (ite (< x 0)
       (+ x (+ 1 UNSIGNED_INT_MAX_{width}))
       x))

; assumes (<= x (* 2 UNSIGNED_INT_MAX_{width}))
(define-fun ubound_int_{width} ((x Int)) Int
  (ite (> x UNSIGNED_INT_MAX_{width})
       (- x (+ 1 UNSIGNED_INT_MAX_{width}))
       x))

(define-fun bound_int_{width} ((x Int)) Int
  (ubound_int_{width}
    (lbound_int_{width} x)))

(define-fun bv_ult_{width} ((x Int) (y Int)) Bool
  (let ((x (bound_int_{width} x))
        (y (bound_int_{width} y)))
       (< x y)))

(define-fun bv_ule_{width} ((x Int) (y Int)) Bool
  (let ((x (bound_int_{width} x))
        (y (bound_int_{width} y)))
       (<= x y)))

(define-fun bv_ugt_{width} ((x Int) (y Int)) Bool
  (bv_ult_{width} y x))

(define-fun bv_uge_{width} ((x Int) (y Int)) Bool
  (bv_ule_{width} y x))

(define-fun bv_same_sign_{width} ((x Int) (y Int)) Bool
  (let ((x (bound_int_{width} x))
        (y (bound_int_{width} y)))
       (or (and (<= x SIGNED_INT_MAX_{width}) (<= y SIGNED_INT_MAX_{width}))
           (and (> x SIGNED_INT_MAX_{width}) (> y SIGNED_INT_MAX_{width})))))

(define-fun bv_slt_{width} ((x Int) (y Int)) Bool
  (let ((x (bound_int_{width} x))
        (y (bound_int_{width} y)))
       (or
         (and (> x SIGNED_INT_MAX_{width})
              (<= y SIGNED_INT_MAX_{width}))
         (and (bv_same_sign_{width} x y)
              (bv_ult_{width} x y)))))

(define-fun bv_sle_{width} ((x Int) (y Int)) Bool
  (let ((x (bound_int_{width} x))
        (y (bound_int_{width} y)))
       (or
         (and (> x SIGNED_INT_MAX_{width})
              (<= y SIGNED_INT_MAX_{width}))
         (and (bv_same_sign_{width} x y)
              (bv_ule_{width} x y)))))

(define-fun bv_sgt_{width} ((x Int) (y Int)) Bool
  (bv_slt_{width} y x))

(define-fun bv_sge_{width} ((x Int) (y Int)) Bool
  (bv_sle_{width} y x))

(define-fun bv_add_{width} ((x Int) (y Int)) Int
  (let ((x (bound_int_{width} x))
        (y (bound_int_{width} y)))
       (bound_int_{width}
         (+ x y))))

(define-fun bv_sub_{width} ((x Int) (y Int)) Int
  (let ((x (bound_int_{width} x))
        (y (bound_int_{width} y)))
       (bound_int_{width}
         (- x y))))

(define-fun bv_neg_{width} ((x Int)) Int
  (let ((x (bound_int_{width} x)))
       (bound_int_{width}
         (- 0 x))))

(define-fun bv_mul_{width} ((x Int) (y Int)) Int
  (let ((x (bound_int_{width} x))
        (y (bound_int_{width} y)))
       {f'(bound_int_{width} ' * width}
           (* x y)
       {f')' * width}))

""".splitlines()

bv_func_mapping = {
    'bvslt': 'bv_slt',
    'bvsle': 'bv_sle',
    'bvsgt': 'bv_sgt',
    'bvsge': 'bv_sge',

    'bvult': 'bv_ult',
    'bvule': 'bv_ule',
    'bvugt': 'bv_ugt',
    'bvuge': 'bv_uge',

    'bvadd': 'bv_add',
    'bvmul': 'bv_mul',
    'bvneg': 'bv_neg',
    'bvsub': 'bv_sub',

    'bvshl': '__NOT_IMPLEMENTED__',
    'bvashr': '__NOT_IMPLEMENTED__',
    'bvlshr': '__NOT_IMPLEMENTED__',

    'bvand': '__NOT_IMPLEMENTED__',
    'bvor': '__NOT_IMPLEMENTED__',
}

def is_bv_type(ast):
    return (type(ast) is list and
            len(ast) == 3 and
            ast[0] == '_' and
            ast[1] == 'BitVec')

def lookup_bv_width_for(name, stacked_symbol_table):
    head, tail = stacked_symbol_table[0], stacked_symbol_table[1:]
    value = head.get(name, None)
    if value:
        if is_bv_type(value):
            return value[2]
        return None
    if len(tail) < 1:
        return None
    return lookup_bv_width_for(name, tail)

def infer_bv_width(ast, stacked_symbol_table):
    if type(ast) is not list:
        return lookup_bv_width_for(ast, stacked_symbol_table)

    if ast[0] == '_' and ast[1].startswith('bv'):
        return ast[2]

    #TODO: This assumes that all BV operations preserve the width.
    #      We might need to improve this later for operations that don't
    widths = [lookup_bv_width_for(e, stacked_symbol_table)
              for e in ast[1:] if type(e) is not list]
    widths = list(set(filter(None, widths)))

    if len(widths) > 1:
        raise Exception(f'Ambiguous BitVec width: {serialize(ast)}')
    if len(widths) == 1:
        return widths[0]

    for arg in ast[1:]:
        width = infer_bv_width(arg, stacked_symbol_table)
        if width:
            return width
    return None

def replace_bv_type(ast):
    if type(ast) is not list:
        return ast
    if is_bv_type(ast):
        return 'Int'
    return [replace_bv_type(e) for e in ast]

def replace_bv_expr(ast, stacked_symbol_table):
    if type(ast) is not list:
        return ast

    if ast[0] == 'declare-fun':
        ast[2] = replace_bv_type(ast[2])
        return ast

    if ast[0] == 'define-fun':
        stacked_symbol_table.insert(0, dict())
        for arg in ast[2]:
            stacked_symbol_table[0][arg[0]] = arg[1]
            arg[1] = replace_bv_type(arg[1])
        ast[4] = replace_bv_expr(ast[4], stacked_symbol_table)
        stacked_symbol_table = stacked_symbol_table[1:]
        return ast

    if ast[0] == 'forall' or ast[0] == 'exists':
        stacked_symbol_table.insert(0, dict())
        var_width_dict = dict()
        for arg in ast[1]:
            stacked_symbol_table[0][arg[0]] = arg[1]
            if is_bv_type(arg[1]):
                var_width_dict[arg[0]] = arg[1][2]
            arg[1] = replace_bv_type(arg[1])
        if len(var_width_dict) < 1:
            ast[2] = replace_bv_expr(ast[2], stacked_symbol_table)
        elif len(var_width_dict) == 1:
            var, width = list(var_width_dict.items())[0]
            ast[2] = replace_bv_expr(ast[2], stacked_symbol_table)
            if type(ast[2]) is list and ast[2][0] == '=>':
                ast[2][1] = ['and', [f'is_int_{width}', var], ast[2][1]]
            else:
                ast[2] = ['=>', [f'is_int_{width}', var], ast[2]]
        else:
            bounded_vars = [[f'is_int_{width}', var]
                            for var, width in var_width_dict.items()]
            bounded_vars.insert(0, 'and')
            ast[2] = replace_bv_expr(ast[2], stacked_symbol_table)
            if type(ast[2]) is list and ast[2][0] == '=>':
                ast[2][1] = ['and', bounded_vars, ast[2][1]]
            else:
                ast[2] = ['=>', bounded_vars, ast[2]]
        stacked_symbol_table = stacked_symbol_table[1:]
        return ast

    if ast[0] == 'let':
        stacked_symbol_table.insert(0, dict())
        for arg in ast[1]:
            if type(arg[1]) is list:
                if arg[1][0] in bv_func_mapping:
                    width = infer_bv_width(arg[1], stacked_symbol_table)
                    arg[1] = replace_bv_expr(arg[1], stacked_symbol_table)
                    stacked_symbol_table[0][arg[0]] = ['_', 'BitVec', width]
                else:
                    arg[1] = replace_bv_expr(arg[1], stacked_symbol_table)
            else:
                width = lookup_bv_width_for(arg[1], stacked_symbol_table)
                if width:
                    stacked_symbol_table[0][arg[0]] = ['_', 'BitVec', width]
        ast[2] = replace_bv_expr(ast[2], stacked_symbol_table)
        stacked_symbol_table = stacked_symbol_table[1:]
        return ast

    if len(ast) == 3 and ast[0] == '_' and ast[1].startswith('bv'):
        return ast[1][2:]

    if type(ast[0]) is str:
        mapped_func = bv_func_mapping.get(ast[0], None)
        if mapped_func:
            if mapped_func == '__NOT_IMPLEMENTED__':
                raise NotImplementedError(f'BitVec operation {ast[0]} has not been implemented.')
            else:
                width = infer_bv_width(ast, stacked_symbol_table)
                if not width:
                    raise NotImplementedError(f'sym_tab = {stacked_symbol_table}\nexpr = {serialize(expr)}')
                ast[0] = f'{mapped_func}_{width}'

    return [replace_bv_expr(e, stacked_symbol_table) for e in ast]

def main(args):
    i_expr = pp.QuotedString(quoteChar='"') | pp.QuotedString(quoteChar='|', unquoteResults=False)
    s_expr = pp.nestedExpr(opener='(', closer=')', ignoreExpr=i_expr)
    s_expr.ignore(';' + pp.restOfLine)

    parser = pp.ZeroOrMore(s_expr)
    ast = parser.parseFile(args.input_file, parseAll=True).asList()

    bv_widths = extract_bv_widths(ast)
    if len(bv_widths) < 1:
        sys.stdout.writelines(serialize(statement) + '\n' for statement in ast)
        return

    stacked_symbol_table = []
    stacked_symbol_table.insert(0, dict())

    for i,statement in enumerate(ast):
        if statement[0] == 'define-fun':
            stacked_symbol_table[statement[1]] = statement[3]
        elif statement[0] == 'declare-const':
            stacked_symbol_table[statement[1]] = statement[2]
        ast[i] = replace_bv_expr(statement, stacked_symbol_table)

    for statement in ast:
        if extract_bv_widths(statement):
            raise NotImplementedError(serialize(statement))

    set_logic_index = next((i for i,e in enumerate(ast) if e[0] == 'set-logic'), None)
    if set_logic_index is None:
        ast[0:0] = ['set-logic' , 'HORN']
        set_logic_index = 0

    set_logic_index += 1
    for width in bv_widths:
        ast[set_logic_index:set_logic_index] = generate_bv_functions(width)

    sys.stdout.writelines(serialize(statement) + '\n' for statement in ast)

if __name__ == '__main__':
    parser = ArgumentParser(formatter_class=ArgumentDefaultsHelpFormatter)

    parser.add_argument(
        'input_file', type=FileType('r'),
        help='Path to an input file (or stdin if "-")')

    main(parser.parse_args())
