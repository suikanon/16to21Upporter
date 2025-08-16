import math
import numpy

def pesToNumpy(matrix):
	return numpy.array([
		matrix[0:4],
		matrix[4:8],
		matrix[8:12],
		[0, 0, 0, 1],
	])
