import gmsh
import os
import sympy as sp
import spylizard as sl

class output(object):
    """ Context manager for temporary changing the working directory <"""
    def __init__(self, folder):
        self.old_workdir = os.getcwd()
        self.new_workdir = folder
    def __enter__(self):
        try:
            os.mkdir(self.new_workdir)
        except FileExistsError:
            pass
        os.chdir(self.new_workdir)
    def __exit__(self, type, value, traceback):
        os.chdir(self.old_workdir)    


def merge_in_gmsh(directory, filter=None):
    """ Plot all files from directory in gmsh
        after applying filter. Filter is required to be a 
        function which takes in a list of filenames and returns a list 
        of filenames to be plotter 
    """
    if filter == None:
        # by default, plot all .pos files
        filter = lambda fs: [f for f in fs if f[-4:] == ".pos"]

    # remove old
    for t in gmsh.view.getTags():
        gmsh.view.remove(t)
    
    # load in new
    with output(directory):
        files = filter(os.listdir())
        files.sort()
        for f in files: 
            gmsh.merge(f)
                
        
from functools import reduce

_lizardify_default_rewrite_rules = {
    'log': sl.log10,
    'sin': sl.sin,
    'cos': sl.cos,
    'tan': sl.tan,
    'asin': sl.asin,
    'acos': sl.acos,
    'atan': sl.atan,
    'Abs': sl.abs,
    'atan2': sl.atan2,
}

def _get_name(o):
    # matrices work differently
    if isinstance(o, sp.MatrixBase):
        return "Matrix"
    return o.func.__name__ 

def lizardify(subs, expr_in, rewrite_overrides={}):
    """ Take a sympy symbolic expression and convert it into 
    sparselizard's expression object.

    Inputs: 
       subs: 
           a dictionary {sympyexpr: sl.expression/sl.parameter/number} for substituting 
           symbols present in the sympy expression. 
       expr_in: 
           the sympy expression
       rewrite_overrides: 
           a dict mapping str -> function(sp.expr,...) sl.expr/parameter/number... for providing 
           custom overrides for specific functions and sympy expressions other than plain symbols. 
           E.g. {'tan2': lambda y,x: sl.tan(y/x)}

    Example:
       # symbols for coordinates
       x = sp.Symbol("x")
       y = sp.Symbol("y")

       # a complicated expression
       a = sp.sin(x) + sp.cos(y)

       # get the fields for coordinates and input them to function
       xf = sl.field("x")
       yf = sl.field("y")

       # convert to an sl expression 
       myexpr = spylizardify({x:xf, y:yf}, a)
              
       # read in a mesh and write the expression 
       mesh = sl.mesh(<read some mesh in>)
       all = sl.selectall()
       myexpr.write(all, "myexpr.pos", 1)
    """
    
    rewrite_rules = {**_lizardify_default_rewrite_rules, **rewrite_overrides}
    
    def doit(expr):
        ename = _get_name(expr)

        if ename in rewrite_rules:
            # check if there is a rewrite rule and apply that
            return rewrite_rules[ename](*map(doit, expr.args))
        elif ename == "Add":
            return reduce(lambda x,y: x+y, map(doit, expr.args))
        elif ename == "Mul": 
            return reduce(lambda x,y: x*y, map(doit, expr.args))
        elif ename == "Pow":
            # assume only two terms, exponentee and exponent
            e,p = expr.args

            # obey the sl style x/y = x * 1/y instead of
            # sympys x/y = x * y ^(-1)
            if isinstance(p, sp.core.numbers.NegativeOne):
                return 1/doit(e)
            
            return sl.pow(doit(e), doit(p))
        elif ename == "Matrix":
            return sl.expression(expr.rows, expr.cols, list(map(doit, expr)))
        elif ename == "Symbol":            
            return subs[expr]
        else:
            # number or something like that,
            # sparselizard seems to work best with floats
            # if this barfs, expr might not be supported
            try:
                return float(expr)
            except TypeError as e:
                raise TypeError(f'A term of type "{ename}" could not be converted to a '
                                "sparselizard expression. This might mean SL doesn't "
                                f'support it. The full error message was "{e}". '
                                f'The term was {expr}')

    return doit(expr_in)


