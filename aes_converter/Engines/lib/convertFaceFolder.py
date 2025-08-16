import base64
import os
import struct
import sys
from xml.etree import ElementTree

from .util import ijoin
from . import fmdl2model, material

def parseFpkXml(xmlPath, containingDirectory):
	output = []
	faceFpkRoot = ElementTree.parse(xmlPath).getroot()
	if faceFpkRoot.tag != "ArchiveFile":
		print("WARNING: Invalid .fpk.xml file '%s', skipping" % xmlPath)
		return output
	for entriesTag in faceFpkRoot:
		if entriesTag.tag == "Entries":
			for entryTag in entriesTag:
				path = entryTag.attrib["FilePath"]
				fullPath = ijoin(containingDirectory, path)
				if fullPath is None:
					print("WARNING: Nonexistent file '%s' referenced by '%s', skipping" % (path, xmlPath))
					continue
				output.append(fullPath)
	return output

def convertBootsFolder(sourceDirectory, destinationDirectory, commonDestinationDirectory):
	bootsFmdlFilename = ijoin(sourceDirectory, "boots.fmdl")
	if bootsFmdlFilename is None:
		print("WARNING: Boots folder '%s' does not contain boots.fmdl" % sourceDirectory)
		return
	
	fmdlFile = fmdl2model.loadFmdl(bootsFmdlFilename)
	fmdl = (bootsFmdlFilename, os.path.dirname(bootsFmdlFilename), fmdlFile)
	
	(materialFile, fmdlMeshMaterialNames) = material.buildMaterials([fmdl], destinationDirectory, commonDestinationDirectory)
	open(os.path.join(destinationDirectory, "boots.mtl"), 'wb').write(materialFile)
	
	modelFile = fmdl2model.convertFmdl(fmdlFile, fmdlMeshMaterialNames)
	fmdl2model.saveModel(modelFile, os.path.join(destinationDirectory, "boots.model"))

def convertGlovesFolder(sourceDirectory, destinationDirectory, commonDestinationDirectory):
	gloveLFilename = ijoin(sourceDirectory, "glove_l.fmdl")
	gloveRFilename = ijoin(sourceDirectory, "glove_r.fmdl")
	
	fmdls = []
	if gloveLFilename is None:
		gloveLFmdlFile = None
	else:
		gloveLFmdlFile = fmdl2model.loadFmdl(gloveLFilename)
		fmdls.append((gloveLFilename, os.path.dirname(gloveLFilename), gloveLFmdlFile))
	if gloveRFilename is None:
		gloveRFmdlFile = None
	else:
		gloveRFmdlFile = fmdl2model.loadFmdl(gloveRFilename)
		fmdls.append((gloveRFilename, os.path.dirname(gloveRFilename), gloveRFmdlFile))
	
	(materialFile, fmdlMeshMaterialNames) = material.buildMaterials(fmdls, destinationDirectory, commonDestinationDirectory)
	open(os.path.join(destinationDirectory, "materials.mtl"), 'wb').write(materialFile)
	
	if gloveLFmdlFile is not None:
		modelFile = fmdl2model.convertFmdl(gloveLFmdlFile, fmdlMeshMaterialNames)
		fmdl2model.saveModel(modelFile, os.path.join(destinationDirectory, "glove_l.model"))
	if gloveRFmdlFile is not None:
		modelFile = fmdl2model.convertFmdl(gloveRFmdlFile, fmdlMeshMaterialNames)
		fmdl2model.saveModel(modelFile, os.path.join(destinationDirectory, "glove_r.model"))

def faceDiffFileIsEmpty(faceDiffBin):
	(xScale, yScale, zScale) = struct.unpack('< 3f', faceDiffBin[8:20])
	return xScale < 0.1 and yScale < 0.1 and zScale < 0.1

def convertFaceFolder(sourceDirectories, destinationDirectory, commonDestinationDirectory):
	faceDiffBinFilename = None
	fmdlFiles = []
	
	for directory in sourceDirectories:
		faceFpkFilename = ijoin(directory, "face.fpk.xml")
		bootsFpkFilename = ijoin(directory, "boots.fpk.xml")
		gloveFpkFilename = ijoin(directory, "glove.fpk.xml")
		
		fpkFilenames = [filename for filename in [
			ijoin(directory, "face.fpk.xml"),
			ijoin(directory, "boots.fpk.xml"),
			ijoin(directory, "glove.fpk.xml"),
		] if filename is not None]
		
		if len(fpkFilenames) == 0:
			print("WARNING: No .xpk.fml file found in model folder '%s', skipping folder" % (directory))
			continue
		if len(fpkFilenames) > 1:
			print("WARNING: Multiple .xpk.fml file found in model folder '%s', skipping folder" % (directory))
			continue
		
		for filename in parseFpkXml(fpkFilenames[0], directory):
			if filename.lower().endswith("face_diff.bin"):
				faceDiffBinFilename = filename
			elif filename.lower().endswith(".fmdl"):
				fmdlFiles.append(filename)
			elif filename.lower().endswith("boots.skl"):
				continue
			else:
				print("WARNING: Unknown file '%s' referenced by '%s', skipping" % (filename, fpkFilenames[0]))
				continue
	
	fmdls = []
	for filename in fmdlFiles:
		containingDirectory = os.path.dirname(filename)
		fmdlFile = fmdl2model.loadFmdl(filename)
		
		fmdls.append((filename, containingDirectory, fmdlFile))
	
	(materialFile, fmdlMeshMaterialNames) = material.buildMaterials(fmdls, destinationDirectory, commonDestinationDirectory)
	open(os.path.join(destinationDirectory, 'materials.mtl'), 'wb').write(materialFile)
	
	for (filename, containingDirectory, fmdlFile) in fmdls:
		baseName = os.path.basename(filename)[:-5].lower()
		
		if 'face_high' in baseName:
			modelType = 'face_neck'
			modelSubtype = 'face'
		elif 'hair_high' in baseName:
			modelType = 'face_neck'
			modelSubtype = 'hair'
		elif 'oral' in baseName:
			modelType = 'face_neck'
			modelSubtype = 'oral'
		elif 'boots' in baseName:
			modelType = 'parts'
			modelSubtype = 'body'
		elif 'glove_l' in baseName:
			baseName = baseName.replace("glove_l", "gloveL")
			modelType = 'gloveL'
			modelSubtype = None
		elif 'glove_r' in baseName:
			baseName = baseName.replace("glove_r", "gloveR")
			modelType = 'gloveR'
			modelSubtype = None
		else:
			modelType = 'parts'
			modelSubtype = baseName
		
		suffixIndex = 0
		while True:
			if suffixIndex == 0:
				suffixComponent = ""
			else:
				suffixComponent = "_%s" % suffixIndex
				suffixIndex += 1
			
			if modelSubtype is None:
				subtypeComponent = ""
			else:
				subtypeComponent = "_%s" % modelSubtype
			
			typeComponent = modelType.replace("_", "").lower()
			
			modelFilename = "%s%s%s.model" % (typeComponent, subtypeComponent, suffixComponent)
			modelPath = os.path.join(destinationDirectory, modelFilename)
			if not os.path.exists(modelPath):
				break
		
		modelFile = fmdl2model.convertFmdl(fmdlFile, fmdlMeshMaterialNames)
		fmdl2model.saveModel(modelFile, modelPath)
	
	if faceDiffBinFilename is not None:
		faceDiffBin = open(faceDiffBinFilename, 'rb').read()
		if not faceDiffFileIsEmpty(faceDiffBin):
			open(os.path.join(destinationDirectory, "face_diff.bin"), 'wb').write(faceDiffBin)

if __name__ == "__main__":
	if len(sys.argv) < 2:
		print("Usage: convertFaceFolder <face folder> [boots folder] [gloves folder]")
		sys.exit(1)
	
	convertFaceFolder(sys.argv[1:], ".", "../../Common")
