# standard modules
import logging
# 3rd party
import numpy
import scipy
import pandas
# PFP modules

logger = logging.getLogger("pfp_log")

def Despike_Mauder_2013(dataframe, **kw):
    """
    Shortcut for:
     opf_func_corrections.__despike__(dataframe, method="mauder2013", q=7)
    """
    kw.update({"method": "mauder2013"})
    return __Despike__(dataframe, **kw)

def __Despike__(dataframe, method="mauder2013", **kwargs):
    """
    Purpose:
     Function to despike columns in a DataFrame.
    Usage:
     opf_func_corrections.Despike(dataframe)
    Author: PHHC
    Date: October 2023
    """
    if method == "mauder2013": despikecorrection = __mauder2013__
    else:
        msg = " Despike method not found. Choose between: Mauder et al. 2013 (mauder2013), ."
        logger.error(msg)
        raise(msg)
    
    dataframe2 = {}

    for c in dataframe:
        var_out = dataframe[c]
        ogap = numpy.isnan(var_out)

        # filter off absurd values 3 orders 
        # of magnitude smaller (bigger) than
        # the 1% (99%) percentile 
        p1 = numpy.nanquantile(var_out, 0.01)
        p99 = numpy.nanquantile(var_out, 0.99)
        absurdity_bounds_min = 10**(-3 if p1 > 0 else 3) * p1
        absurdity_bounds_max = 10**(3 if p99 > 0 else -3) * p99

        absurd_cases = sum(numpy.where((var_out < absurdity_bounds_min) * (var_out > absurdity_bounds_max), 1, 0))
        if absurd_cases:
            msg = ' Ignoring ' + str(absurd_cases) + ' absurd values lower than ' 
            msg = msg + str(absurdity_bounds_min) + ' and higher than ' 
            msg = msg + str(absurdity_bounds_max) + ' in variable ' + str(c)
            logger.info(msg)

            var_out = numpy.where(var_out < absurdity_bounds_min, numpy.nan, var_out)
            var_out = numpy.where(var_out > absurdity_bounds_max, numpy.nan, var_out)
        
        var_out = despikecorrection(var_out, **kwargs)
        
        ngap = numpy.isnan(var_out)
        N = len(var_out)
        
        var_out = numpy.interp(numpy.linspace(0, 1, N),
                            numpy.linspace(0, 1, N)[ngap == False],
                            var_out[ngap == False])
        var_out = numpy.where(ogap, numpy.nan, var_out)

        dataframe2[c] = var_out
    return pandas.DataFrame(dataframe2)

def __mauder2013__(x, q=7):
    """
    Despike from Mauder et al. (2013)
    """
    x = numpy.array(x)
    x_med = numpy.nanmedian(x)
    mad = numpy.nanmedian(numpy.abs(x - x_med))
    bounds = (x_med - (q * mad) / 0.6745, x_med + (q * mad) / 0.6745)
    
    x[x < min(bounds)] = numpy.nan
    x[x > max(bounds)] = numpy.nan
    return x

def Tilt_2_rotation(dataframe, u="u", v="v", w="w", **kw):
    kw.update(method='2r')
    return __Tilt_correction__(dataframe, u, v, w, **kw)

def Tilt_3_rotation(dataframe, u="u", v="v", w="w", **kw):
    kw.update(method='2r')
    return __Tilt_correction__(dataframe, u, v, w, **kw)

def Tilt_planar_fit(dataframe, u="u", v="v", w="w", **kw):
    kw.update(method='pf')
    return __Tilt_correction__(dataframe, u, v, w, **kw)

def __Tilt_correction__(dataframe, u="u", v="v", w="w", method='2r', **kwargs):
    """
    Purpose:
     Function to apply tilt correction on 3d wind observations.
    Usage:
     opf_func_corrections.Tilt_correction(u, v, w, method)
     where method must be: 2r (double rotation), 3r (triple 
     rotation), or pf (planar fit)
    Author: PHHC
    Date: October 2023
    """
    if method == '2r': tiltcorrection = __wilczak2001_2r__
    elif method == '3r': tiltcorrection = __wilczak2001_3r__
    elif method == 'pf': tiltcorrection = __planarfit__
    else:
        msg = " Tilt method not found. Choose between: double rotation (2r), triple rotation (3r), and planar fit (pf)."
        logger.error(msg)
        raise(msg)
    
    dataframe2 = {}

    # Add save pre calculus in file
    # read and write like EddyPro
    dataframe2[u], dataframe2[v], dataframe2[w], _ = tiltcorrection(
        dataframe[u], dataframe[v], dataframe[w], **kwargs)
    
    return dataframe2

def __wilczak2001_2r__(u, v, w, _theta=None, _phi=None):
    """
    Tilt correction from Wilczak et al., 2001
    double (and triple) rotation should be done in loops of 30 minutes
    """
    #first rotation
    if _theta is None:
        _theta = numpy.arctan(numpy.nanmean(v)/numpy.nanmean(u))
    u1 = u * numpy.cos(_theta) + v * numpy.sin(_theta)
    v1 = -u * numpy.sin(_theta) + v * numpy.cos(_theta)
    w1 = w

    #second rotation
    if _phi is None:
        _phi = numpy.arctan(numpy.nanmean(w1)/numpy.nanmean(u1))
    u2 = u1 * numpy.cos(_phi) + w1 * numpy.sin(_phi)
    v2 = v1
    w2 = -u1 * numpy.sin(_phi) + w1 * numpy.cos(_phi)
        
    return u2, v2, w2, (_theta, _phi)


def __wilczak2001_3r__(u, v, w, _psi=None):
    """
    Tilt correction from Wilczak et al., 2001
    double (and triple) rotation should be done in loops of 30 minutes
    """
    u2, v2, w2 = __wilczak2001_2r__(u, v, w)
    
    #third rotation
    if _psi is None:
        _psi = numpy.arctan((2 * numpy.nanmean(v2 * w2)) / (numpy.nanmean(v2**2) - numpy.nanmean(w2**2)))
    u3 = u2
    v3 = v2 * numpy.cos(_psi) + w2 * numpy.sin(_psi)
    w3 = -v2 * numpy.sin(_psi) + w2 * numpy.cos(_psi)
    
    return u3, v3, w3, (_psi)


def __planarfit__(u, v, w):
    """
    Tilt correction from Wilczak et al., 2001
    planar fit rotation should be done over long periods
    """
    meanU = numpy.nanmean(u)
    meanV = numpy.nanmean(v)
    meanW = numpy.nanmean(w)

    def findB(meanU, meanV, meanW):
        su = numpy.nansum(meanU)
        sv = numpy.nansum(meanV)
        sw = numpy.nansum(meanW)

        suv = meanU * meanV
        suw = meanU * meanW
        svw = meanV * meanW
        su2 = meanU * meanU
        sv2 = meanV * meanV

        H = numpy.matrix([[1, su, sv], [su, su2, suv], [sv, suv, sv2]])
        g = numpy.matrix([sw, suw, svw]).T
        x = scipy.linalg.solve(H, g)

        b0 = x[0][0]
        b1 = x[1][0]
        b2 = x[2][0]
        return b0, b1, b2
    
    b0, b1, b2 = findB(meanU,meanV,meanW)

    Deno = numpy.sqrt(1 + b1 **2 + b2 **2)
    p31 = -b1 / Deno
    p32 = -b2 / Deno
    p33 = 1 / Deno

    cosγ = p33 / numpy.sqrt(p32**2+p33**2)
    sinγ = -p32 / numpy.sqrt(p32**2 + p33**2)
    cosβ = numpy.sqrt(p32**2 + p33**2)
    sinβ = p31

    R2 = numpy.matrix([[1, 0, 0],
                    [0, cosγ, -sinγ],
                    [0, sinγ, cosγ]])
    R3 = numpy.matrix([[cosβ, 0, sinβ],
                    [0, 1, 0],
                    [-sinβ, 0, cosβ]])

    A0 = R3.T * R2.T * [[meanU], [meanV], [meanW]]

    α = numpy.arctan2(A0[1].tolist()[0][0],
                   A0[0].tolist()[0][0])

    R1 = numpy.matrix([[numpy.cos(α), -numpy.sin(α), 0],
                    [numpy.sin(α), numpy.cos(α), 0], 
                    [0, 0, 1]])

    A1 = R1.T * ((R3.T * R2.T) * numpy.matrix([u, v, w - b0]))

    U1 = numpy.array(A1[0])[0]
    V1 = numpy.array(A1[1])[0]
    W1 = numpy.array(A1[2])[0]
        
    return U1, V1, W1, (R1, R2, R3, b0)

    
def __tiltcorrection__(*args, method='2r', **kwargs):
    """
    Purpose:
     Function to apply tilt correction on 3d wind observations.
    Usage:
     opf_func_corrections.Tilt_correction(u, v, w, method)
     where method must be: 2r (double rotation), 3r (triple 
     rotation), or pf (planar fit)
    Author: PHHC
    Date: October 2023
    """
    if method == '2r': return __wilczak2001_2r__(*args, **{k: v for k, v in kwargs.items() if k in ['u', 'v', 'w', '_theta', '_phi', 'verbosity']})
    if method == '3r': return __wilczak2001_3r__(*args, **kwargs)
    if method == 'pf': return __planarfit__(*args, **kwargs)
    else:
        msg = " Tilt method not found. Choose between: double rotation (2r), triple rotation (3r), and planar fit (pf)."
        logger.error(msg)
        raise(msg)
    