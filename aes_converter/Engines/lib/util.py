import fnmatch
import os

def ijoin(directory, filename):
	parts = filename.split('/')
	for part in parts:
		if part == '.':
			continue
		items = [os.path.join(directory, f) for f in os.listdir(directory) if f.lower() == part.lower()]
		if len(items) == 0:
			return None
		else:
			directory = items[0]
	return directory

def iglob(directory, pattern):
	parts = pattern.split('/')
	matches = [directory]
	for part in parts:
		if part == '.':
			continue
		nextMatches = []
		for match in matches:
			nextMatches += [os.path.join(match, f) for f in os.listdir(match) if fnmatch.fnmatch(f.lower(), part.lower())]
		matches = nextMatches
	return matches

