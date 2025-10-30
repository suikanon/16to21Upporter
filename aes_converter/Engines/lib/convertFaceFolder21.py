import os
import shutil
import struct
import sys

from .util import ijoin, iglob
from . import model2fmdl, material
from . import FmdlFile, ModelFile


def convertBootsFolder(sourceDirectory, destinationDirectory, commonDestinationDirectory, bootsSklPath):
	"""
	Convert a PES16 boots folder to PES21 format.

	Args:
	    sourceDirectory: Path to source boots folder (PES16 with .model files)
	    destinationDirectory: Path to destination boots folder (PES21 with .fmdl files)
	    commonDestinationDirectory: Path to common textures folder (unused for PES21)
	    bootsSklPath: Path to the boots.skl skeleton file to copy
	"""
	# Find boots.model file
	bootsModelFile = ijoin(sourceDirectory, "boots.model")
	if bootsModelFile is None:
		print("WARNING: Boots folder '%s' does not contain boots.model" % sourceDirectory)
		return

	# Convert .model to .fmdl
	try:
		modelFileObj = model2fmdl.loadModel(bootsModelFile)
		outputFmdl = os.path.join(destinationDirectory, "boots.fmdl")
		model2fmdl.saveFmdl(model2fmdl.convertModel(modelFileObj), outputFmdl)
	except Exception as e:
		print(f"WARNING: Failed to convert boots.model: {e}")
		return

	# Copy boots.skl skeleton file
	if bootsSklPath and os.path.exists(bootsSklPath):
		shutil.copy(bootsSklPath, os.path.join(destinationDirectory, "boots.skl"))
	else:
		print("WARNING: boots.skl not found, boots folder may not work correctly")

	# Create boots.fpk.xml
	fpkXml = os.path.join(destinationDirectory, "boots.fpk.xml")
	with open(fpkXml, 'w', encoding='utf-8') as f:
		f.write('<?xml version="1.0"?>\n')
		f.write('<ArchiveFile xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema" xsi:type="FpkFile" Name="boots.fpk" FpkType="Fpk">\n')
		f.write('  <Entries>\n')
		f.write('    <Entry FilePath="boots.skl" />\n')
		f.write('    <Entry FilePath="boots.fmdl" />\n')
		f.write('  </Entries>\n')
		f.write('  <References />\n')
		f.write('</ArchiveFile>\n')

	# Copy all texture files (.dds, .ftex)
	for ext in ['*.dds', '*.ftex']:
		textureFiles = iglob(sourceDirectory, ext)
		for texFile in textureFiles:
			shutil.copy(texFile, os.path.join(destinationDirectory, os.path.basename(texFile)))


def convertGlovesFolder(sourceDirectory, destinationDirectory, commonDestinationDirectory):
	"""
	Convert a PES16 gloves folder to PES21 format.

	Args:
	    sourceDirectory: Path to source gloves folder (PES16 with .model files)
	    destinationDirectory: Path to destination gloves folder (PES21 with .fmdl files)
	    commonDestinationDirectory: Path to common textures folder (unused for PES21)
	"""
	# Convert left and right glove .model files to .fmdl
	hasGloves = False
	for gloveName in ["glove_l", "glove_r"]:
		gloveModelFile = ijoin(sourceDirectory, f"{gloveName}.model")
		if gloveModelFile is not None:
			try:
				modelFileObj = model2fmdl.loadModel(gloveModelFile)

				model = (gloveModelFile, os.path.dirname(gloveModelFile), modelFileObj)
				(materialFile, fmdlMeshMaterialNames) = material.buildFmdlMaterials([model], destinationDirectory,
																				commonDestinationDirectory)
				outputFmdl = os.path.join(destinationDirectory, f"{gloveName}.fmdl")
				model2fmdl.saveFmdl(model2fmdl.convertModel(modelFileObj, fmdlMeshMaterialNames), outputFmdl)
				hasGloves = True
			except Exception as e:
				print(f"WARNING: Failed to convert {gloveName}.model: {e}")

	if not hasGloves:
		print("WARNING: Gloves folder '%s' does not contain glove_l.model or glove_r.model" % sourceDirectory)
		return

	# Create glove.fpk.xml
	fpkXml = os.path.join(destinationDirectory, "glove.fpk.xml")
	with open(fpkXml, 'w', encoding='utf-8') as f:
		f.write('<?xml version="1.0"?>\n')
		f.write('<ArchiveFile xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema" xsi:type="FpkFile" Name="glove.fpk" FpkType="Fpk">\n')
		f.write('  <Entries>\n')
		f.write('    <Entry FilePath="glove_l.fmdl" />\n')
		f.write('    <Entry FilePath="glove_r.fmdl" />\n')
		f.write('  </Entries>\n')
		f.write('  <References />\n')
		f.write('</ArchiveFile>\n')

	# Copy all texture files (.dds, .ftex)
	for ext in ['*.dds', '*.ftex']:
		textureFiles = iglob(sourceDirectory, ext)
		for texFile in textureFiles:
			shutil.copy(texFile, os.path.join(destinationDirectory, os.path.basename(texFile)))

def faceDiffFileIsEmpty(faceDiffBin):
	(xScale, yScale, zScale) = struct.unpack('< 3f', faceDiffBin[8:20])
	return xScale < 0.1 and yScale < 0.1 and zScale < 0.1


def buildFmdlMaterials():
	material = FmdlFile.FmdlFile.MaterialInstance()

	return


def convertFaceFolder(sourceDirectories, destinationDirectory, commonDestinationDirectory, bootsSklPath, playerFolderName=None, bootsGlovesBaseId=None, relativePlayerId=None):
	"""
	Convert a PES16 face folder (unified face/boots/gloves) to PES21 format.

	Args:
	    sourceDirectories: List of source face folders (PES16 with .model files)
	    destinationDirectory: Path to destination root folder (PES21 with separate Faces/Boots/Gloves folders)
	    commonDestinationDirectory: Path to common textures folder (unused for PES21)
	    bootsSklPath: Path to the boots.skl skeleton file to copy to boots folders
	    playerFolderName: Name to use for the player subfolders (e.g., "XXX01 - Snuffy")
	    bootsGlovesBaseId: Base ID for calculating boots/gloves IDs (from team)
	    relativePlayerId: Player number within team (1-23)
	"""
	# Determine folder name from the first source directory if not provided
	if playerFolderName is None and len(sourceDirectories) > 0:
		playerFolderName = os.path.basename(sourceDirectories[0])

	# Calculate boots/gloves ID and extract player name for k#### format
	sharedBootsFolderName = None
	sharedGlovesFolderName = None
	if bootsGlovesBaseId is not None and relativePlayerId is not None:
		bootsId = bootsGlovesBaseId + relativePlayerId
		# Extract player name from playerFolderName (format: "XXX01 - PlayerName")
		if playerFolderName and " - " in playerFolderName:
			playerName = playerFolderName.split(" - ", 1)[1]
		else:
			playerName = playerFolderName if playerFolderName else "Player"
		sharedBootsFolderName = f"k{bootsId:04d} - {playerName}"
		sharedGlovesFolderName = f"g{bootsId:04d} - {playerName}"

	# Collect all .model files from all source directories
	faceModels = []  # face_neck type models
	bootsModels = []  # parts/uniform type models
	gloveModels = []  # gloveL/gloveR type models
	faceDiffBinFilename = None
	portraitFilename = None
	allTextureFiles = []

	for directory in sourceDirectories:
		# Find all .model files
		modelFiles = iglob(directory, "*.model")

		for modelFile in modelFiles:
			baseName = os.path.basename(modelFile)[:-6].lower()  # Remove .model extension

			# Categorize by type based on filename
			if 'face' in baseName or 'hair' in baseName:
				print("adding face")
				faceModels.append(modelFile)
			elif 'glove' in baseName or 'hand' in baseName:
				print("adding glove")
				gloveModels.append(modelFile)
			else:
				# Everything else goes to boots (parts/uniform)
				print("adding boots")
				bootsModels.append(modelFile)

		# Look for face_diff.bin
		faceDiffFile = ijoin(directory, "face_diff.bin")
		if faceDiffFile is not None and faceDiffBinFilename is None:
			faceDiffBinFilename = faceDiffFile

		# Look for portrait
		portraitFile = ijoin(directory, "portrait.dds")
		if portraitFile is not None and portraitFilename is None:
			portraitFilename = portraitFile

		# Collect all texture files
		for ext in ['*.dds', '*.ftex']:
			textureFiles = iglob(directory, ext)
			for texFile in textureFiles:
				if 'portrait' not in os.path.basename(texFile).lower():
					allTextureFiles.append(texFile)

	# Convert face models if any exist
	if len(faceModels) > 0:
		# Create Faces/XXX01 - PlayerName/ subfolder
		facesParentFolder = os.path.join(destinationDirectory, "Faces")
		if not os.path.exists(facesParentFolder):
			os.makedirs(facesParentFolder)

		facesFolder = os.path.join(facesParentFolder, playerFolderName)
		if not os.path.exists(facesFolder):
			os.makedirs(facesFolder)

		for modelFile in faceModels:
			baseName = os.path.basename(modelFile)[:-6]  # Remove .model
			try:
				modelFileObj = model2fmdl.loadModel(modelFile)
				outputFmdl = os.path.join(facesFolder, f"{baseName}.fmdl")
				print("converting model")
				print(modelFile)
				print(os.path.dirname(modelFile))
				fmdl = model2fmdl.convertModel(modelFileObj, os.path.dirname(modelFile))
				print("saving face model")
				model2fmdl.saveFmdl(fmdl, outputFmdl)
			except Exception as e:
				print(f"WARNING: Failed to convert {modelFile}: {e}")

		# Copy face_diff.bin if present and not empty
		if faceDiffBinFilename is not None:
			faceDiffBin = open(faceDiffBinFilename, 'rb').read()
			if not faceDiffFileIsEmpty(faceDiffBin):
				shutil.copy(faceDiffBinFilename, os.path.join(facesFolder, "face_diff.bin"))

		# Create face.fpk.xml
		fpkXml = os.path.join(facesFolder, "face.fpk.xml")
		with open(fpkXml, 'w', encoding='utf-8') as f:
			f.write('<?xml version="1.0"?>\n')
			f.write('<ArchiveFile xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema" xsi:type="FpkFile" Name="face.fpk" FpkType="Fpk">\n')
			f.write('  <Entries>\n')

			# Add face_diff.bin if it exists
			if faceDiffBinFilename is not None:
				faceDiffBin = open(faceDiffBinFilename, 'rb').read()
				if not faceDiffFileIsEmpty(faceDiffBin):
					f.write('    <Entry FilePath="face_diff.bin" />\n')

			# Add all face .fmdl files
			for modelFile in faceModels:
				baseName = os.path.basename(modelFile)[:-6]
				f.write(f'    <Entry FilePath="{baseName}.fmdl" />\n')

			f.write('  </Entries>\n')
			f.write('  <References />\n')
			f.write('</ArchiveFile>\n')

		# Copy texture files to faces folder
		for texFile in allTextureFiles:
			shutil.copy(texFile, os.path.join(facesFolder, os.path.basename(texFile)))

		# Copy portrait to this player's Faces folder if it exists
		if portraitFilename is not None:
			shutil.copy(portraitFilename, os.path.join(facesFolder, os.path.basename(portraitFilename)))

	# Convert boots models if any exist
	if len(bootsModels) > 0:
		# Create Boots/k#### - PlayerName/ subfolder
		bootsParentFolder = os.path.join(destinationDirectory, "Boots")
		if not os.path.exists(bootsParentFolder):
			os.makedirs(bootsParentFolder)

		# Use k#### format if bootsGlovesFolderName is available, otherwise use playerFolderName
		bootsFolderName = sharedBootsFolderName if sharedBootsFolderName else playerFolderName
		bootsFolder = os.path.join(bootsParentFolder, bootsFolderName)
		if not os.path.exists(bootsFolder):
			os.makedirs(bootsFolder)

		for modelFile in bootsModels:
			baseName = os.path.basename(modelFile)[:-6]  # Remove .model
			print("converting boots " + baseName)
			try:
				modelFileObj = model2fmdl.loadModel(modelFile)
				outputFmdl = os.path.join(bootsFolder, f"{baseName}.fmdl")
				fmdl = model2fmdl.convertModel(modelFileObj, os.path.dirname(modelFile))
				print("saving boots model")
				model2fmdl.saveFmdl(fmdl, outputFmdl)
			except Exception as e:
				print(f"WARNING: Failed to convert {modelFile}: {e}")

		# Copy boots.skl skeleton file
		if bootsSklPath and os.path.exists(bootsSklPath):
			shutil.copy(bootsSklPath, os.path.join(bootsFolder, "boots.skl"))
		else:
			print("WARNING: boots.skl not found, boots folder may not work correctly")

		# Create boots.fpk.xml
		fpkXml = os.path.join(bootsFolder, "boots.fpk.xml")
		with open(fpkXml, 'w', encoding='utf-8') as f:
			f.write('<?xml version="1.0"?>\n')
			f.write('<ArchiveFile xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema" xsi:type="FpkFile" Name="boots.fpk" FpkType="Fpk">\n')
			f.write('  <Entries>\n')
			f.write('    <Entry FilePath="boots.skl" />\n')

			# Add all boots .fmdl files
			for modelFile in bootsModels:
				baseName = os.path.basename(modelFile)[:-6]
				f.write(f'    <Entry FilePath="{baseName}.fmdl" />\n')

			f.write('  </Entries>\n')
			f.write('  <References />\n')
			f.write('</ArchiveFile>\n')

		# Copy texture files to boots folder
		for texFile in allTextureFiles:
			shutil.copy(texFile, os.path.join(bootsFolder, os.path.basename(texFile)))

	# Convert glove models if any exist
	if len(gloveModels) > 0:
		# Create Gloves/k#### - PlayerName/ subfolder
		glovesParentFolder = os.path.join(destinationDirectory, "Gloves")
		if not os.path.exists(glovesParentFolder):
			os.makedirs(glovesParentFolder)

		# Use k#### format if bootsGlovesFolderName is available, otherwise use playerFolderName
		glovesFolderName = sharedGlovesFolderName if sharedGlovesFolderName else playerFolderName
		glovesFolder = os.path.join(glovesParentFolder, glovesFolderName)
		if not os.path.exists(glovesFolder):
			os.makedirs(glovesFolder)

		for modelFile in gloveModels:
			baseName = os.path.basename(modelFile)[:-6]  # Remove .model
			try:
				modelFileObj = model2fmdl.loadModel(modelFile)
				outputFmdl = os.path.join(glovesFolder, f"{baseName}.fmdl")
				fmdl = model2fmdl.convertModel(modelFileObj, os.path.dirname(modelFile))
				print("saving glove model")
				model2fmdl.saveFmdl(fmdl, outputFmdl)
			except Exception as e:
				print(f"WARNING: Failed to convert {modelFile}: {e}")

		# Create glove.fpk.xml
		fpkXml = os.path.join(glovesFolder, "glove.fpk.xml")
		with open(fpkXml, 'w', encoding='utf-8') as f:
			f.write('<?xml version="1.0"?>\n')
			f.write('<ArchiveFile xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema" xsi:type="FpkFile" Name="glove.fpk" FpkType="Fpk">\n')
			f.write('  <Entries>\n')

			# Add all glove .fmdl files
			for modelFile in gloveModels:
				baseName = os.path.basename(modelFile)[:-6]
				f.write(f'    <Entry FilePath="{baseName}.fmdl" />\n')

			f.write('  </Entries>\n')
			f.write('  <References />\n')
			f.write('</ArchiveFile>\n')

		# Copy texture files to gloves folder
		for texFile in allTextureFiles:
			shutil.copy(texFile, os.path.join(glovesFolder, os.path.basename(texFile)))


if __name__ == "__main__":
	if len(sys.argv) < 2:
		print("Usage: convertFaceFolder <face folder> [boots folder] [gloves folder]")
		sys.exit(1)
	
	convertFaceFolder(sys.argv[1:], ".", "../../Common")
