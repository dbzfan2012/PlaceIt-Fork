import importlib.metadata as md

import astropy.coordinates
import cmaes
import matplotlib
import numpy
import open3d
import pybullet
import pyquaternion
import ribs
import scipy
import sklearn
import transforms3d

import algorithms
import configs
import environments
import utils


print("PlaceIt install check OK")
print("qd_place", md.version("qd_place"))
print("numpy", numpy.__version__)
print("pybullet", pybullet.__version__ if hasattr(pybullet, "__version__") else "imported")
print("open3d", open3d.__version__)
