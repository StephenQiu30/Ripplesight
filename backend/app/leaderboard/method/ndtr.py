"""Double precision Cephes CDF, preserving the upstream v15 error model.

Port of AIHOT method/ndtr.ts (MIT); see ../PROVENANCE.md.
"""

from math import exp, sqrt

_P = (
    2.46196981473530512524e-10,
    5.64189564831068821977e-1,
    7.46321056442269912687,
    48.6371970985681366614,
    196.520832956077098242,
    526.445194995477358631,
    934.528527171957607540,
    1027.55188689515710272,
    557.535335369399327526,
)
_Q = (
    13.2281951154744992508,
    86.7072140885989742329,
    354.937778887819891062,
    975.708501743205489753,
    1823.90916687909736289,
    2246.33760818710981792,
    1656.66309194161350182,
    557.535340817727675546,
)
_R = (
    0.564189583547755073984,
    1.27536670759978104416,
    5.01905042251180477414,
    6.16021097993053585195,
    7.40974269950448939160,
    2.97886665372100240670,
)
_S = (
    2.26052863220117276590,
    9.39603524938001434673,
    12.0489539808096656605,
    17.0814450747565897222,
    9.60896809063285878198,
    3.36907645100081516050,
)
_T = (
    9.60497373987051638749,
    90.0260197203842689217,
    2232.00534594684319226,
    7003.32514112805075473,
    55592.3013010394962768,
)
_U = (
    33.5617141647503099647,
    521.357949780152679795,
    4594.32382970980127987,
    22629.0000613890934246,
    49267.3942608635921086,
)
_MAXLOG = 7.09782712893383996843e2
_SQRT_HALF = sqrt(0.5)


def _polevl(x: float, coefficients: tuple[float, ...]) -> float:
    result = coefficients[0]
    for coefficient in coefficients[1:]:
        result = result * x + coefficient
    return result


def _p1evl(x: float, coefficients: tuple[float, ...]) -> float:
    result = x + coefficients[0]
    for coefficient in coefficients[1:]:
        result = result * x + coefficient
    return result


def erf(x: float) -> float:
    if abs(x) > 1:
        return 1 - erfc(x)
    z = x * x
    return x * _polevl(z, _T) / _p1evl(z, _U)


def erfc(a: float) -> float:
    x = abs(a)
    if x < 1:
        return 1 - erf(a)
    z = -a * a
    if z < -_MAXLOG:
        return 2.0 if a < 0 else 0.0
    p = _polevl(x, _P if x < 8 else _R)
    q = _p1evl(x, _Q if x < 8 else _S)
    y = exp(z) * p / q
    return 2 - y if a < 0 else y


def ndtr(a: float) -> float:
    x = a * _SQRT_HALF
    z = abs(x)
    if z < _SQRT_HALF:
        return 0.5 + 0.5 * erf(x)
    y = 0.5 * erfc(z)
    return 1 - y if x > 0 else y
