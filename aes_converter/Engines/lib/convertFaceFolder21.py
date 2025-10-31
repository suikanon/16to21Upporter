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
	hasFaceHighWin32Only = False  # Track if we only have face_high_win32.model (small size)
	hairHighModel = None  # Track face_high_win32.model if size > 990 bytes

	for directory in sourceDirectories:
		# Find all .model files
		modelFiles = iglob(directory, "*.model")

		for modelFile in modelFiles:
			baseName = os.path.basename(modelFile)[:-6].lower()  # Remove .model extension

			# Special handling for face_high_win32.model
			if baseName == 'face_high_win32':
				fileSize = os.path.getsize(modelFile)
				if fileSize > 990:
					print(f"face_high_win32.model is {fileSize} bytes, will convert to hair_high.fmdl")
					hairHighModel = modelFile
				else:
					print(f"skipping face_high_win32.model ({fileSize} bytes <= 990)")
				continue

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

	# Check if we only have small face_high_win32.model (no other face models)
	# We still need to create the Faces folder in this case
	for directory in sourceDirectories:
		allFaceTypeModels = []
		modelFiles = iglob(directory, "*.model")
		for modelFile in modelFiles:
			baseName = os.path.basename(modelFile)[:-6].lower()
			if 'face' in baseName or 'hair' in baseName:
				# Check if it's a small face_high_win32
				if baseName == 'face_high_win32':
					fileSize = os.path.getsize(modelFile)
					if fileSize <= 990:
						allFaceTypeModels.append(baseName)
				else:
					allFaceTypeModels.append(baseName)

		# If we have small face_high_win32 but no other face models, set the flag
		if 'face_high_win32' in allFaceTypeModels and len(allFaceTypeModels) == 1:
			hasFaceHighWin32Only = True

	# Convert face models if any exist, OR if we have hair_high to convert, OR if we only have small face_high_win32.model, OR if we have a portrait
	if len(faceModels) > 0 or hairHighModel is not None or hasFaceHighWin32Only or portraitFilename is not None:
		# Create Faces/XXX01 - PlayerName/ subfolder
		facesParentFolder = os.path.join(destinationDirectory, "Faces")
		if not os.path.exists(facesParentFolder):
			os.makedirs(facesParentFolder)

		facesFolder = os.path.join(facesParentFolder, playerFolderName)
		if not os.path.exists(facesFolder):
			os.makedirs(facesFolder)

		# Determine which face models to convert and what to name them
		# Track converted files for face.fpk.xml
		convertedFaceFiles = []

		# Handle large face_high_win32.model separately (always becomes hair_high.fmdl)
		if hairHighModel is not None:
			try:
				modelFileObj = model2fmdl.loadModel(hairHighModel)
				outputFmdl = os.path.join(facesFolder, "hair_high.fmdl")
				print("converting face_high_win32.model to hair_high.fmdl")
				fmdl = model2fmdl.convertModel(modelFileObj, os.path.dirname(hairHighModel))
				print("saving hair_high.fmdl")
				model2fmdl.saveFmdl(fmdl, outputFmdl)
				convertedFaceFiles.append("hair_high.fmdl")
			except Exception as e:
				print(f"WARNING: Failed to convert hair_high model: {e}")

		# Process regular face models with intelligent naming
		if len(faceModels) == 1:
			# Single model: always becomes face_high.fmdl
			modelFile = faceModels[0]
			baseName = os.path.basename(modelFile)[:-6]
			try:
				modelFileObj = model2fmdl.loadModel(modelFile)
				outputFmdl = os.path.join(facesFolder, "face_high.fmdl")
				print(f"converting {baseName}.model to face_high.fmdl")
				fmdl = model2fmdl.convertModel(modelFileObj, os.path.dirname(modelFile))
				print("saving face_high.fmdl")
				model2fmdl.saveFmdl(fmdl, outputFmdl)
				convertedFaceFiles.append("face_high.fmdl")
			except Exception as e:
				print(f"WARNING: Failed to convert {modelFile}: {e}")

		elif len(faceModels) == 2:
			# Two models: one becomes face_high.fmdl, the other hair_high.fmdl
			# Prefer the one with "hair" in the name for hair_high.fmdl
			hairModel = None
			faceModel = None

			for modelFile in faceModels:
				baseName = os.path.basename(modelFile)[:-6].lower()
				if 'hair' in baseName:
					hairModel = modelFile
				else:
					faceModel = modelFile

			# If neither has "hair" in the name, use file size to decide
			if hairModel is None:
				print("WARNING: Ambiguous face models - neither has 'hair' in filename, using smaller file as hair_high.fmdl")
				sizes = [(modelFile, os.path.getsize(modelFile)) for modelFile in faceModels]
				sizes.sort(key=lambda x: x[1])  # Sort by size
				hairModel = sizes[0][0]  # Smaller file
				faceModel = sizes[1][0]  # Larger file

			# If both have "hair" or only one was set, assign the other
			if faceModel is None:
				faceModel = faceModels[0] if faceModels[0] != hairModel else faceModels[1]

			# Convert face_high.fmdl
			try:
				baseName = os.path.basename(faceModel)[:-6]
				modelFileObj = model2fmdl.loadModel(faceModel)
				outputFmdl = os.path.join(facesFolder, "face_high.fmdl")
				print(f"converting {baseName}.model to face_high.fmdl")
				fmdl = model2fmdl.convertModel(modelFileObj, os.path.dirname(faceModel))
				print("saving face_high.fmdl")
				model2fmdl.saveFmdl(fmdl, outputFmdl)
				convertedFaceFiles.append("face_high.fmdl")
			except Exception as e:
				print(f"WARNING: Failed to convert face model: {e}")

			# Convert hair_high.fmdl
			try:
				baseName = os.path.basename(hairModel)[:-6]
				modelFileObj = model2fmdl.loadModel(hairModel)
				outputFmdl = os.path.join(facesFolder, "hair_high.fmdl")
				print(f"converting {baseName}.model to hair_high.fmdl")
				fmdl = model2fmdl.convertModel(modelFileObj, os.path.dirname(hairModel))
				print("saving hair_high.fmdl")
				model2fmdl.saveFmdl(fmdl, outputFmdl)
				convertedFaceFiles.append("hair_high.fmdl")
			except Exception as e:
				print(f"WARNING: Failed to convert hair model: {e}")

		elif len(faceModels) > 2:
			# More than two models: keep only the two largest
			print(f"WARNING: Found {len(faceModels)} face models, keeping only the 2 largest")
			modelSizes = [(modelFile, os.path.getsize(modelFile)) for modelFile in faceModels]
			modelSizes.sort(key=lambda x: x[1], reverse=True)  # Sort by size, largest first
			largestTwo = [modelSizes[0][0], modelSizes[1][0]]

			# Determine which is hair based on filename
			hairModel = None
			faceModel = None

			for modelFile in largestTwo:
				baseName = os.path.basename(modelFile)[:-6].lower()
				if 'hair' in baseName:
					hairModel = modelFile
				else:
					faceModel = modelFile

			# If neither has "hair" in the name, use file size
			if hairModel is None:
				print("WARNING: Ambiguous face models - neither has 'hair' in filename, using smaller file as hair_high.fmdl")
				hairModel = modelSizes[1][0]  # Second largest
				faceModel = modelSizes[0][0]  # Largest

			# If both have "hair" or only one was set, assign the other
			if faceModel is None:
				faceModel = largestTwo[0] if largestTwo[0] != hairModel else largestTwo[1]

			# Convert face_high.fmdl
			try:
				baseName = os.path.basename(faceModel)[:-6]
				modelFileObj = model2fmdl.loadModel(faceModel)
				outputFmdl = os.path.join(facesFolder, "face_high.fmdl")
				print(f"converting {baseName}.model to face_high.fmdl")
				fmdl = model2fmdl.convertModel(modelFileObj, os.path.dirname(faceModel))
				print("saving face_high.fmdl")
				model2fmdl.saveFmdl(fmdl, outputFmdl)
				convertedFaceFiles.append("face_high.fmdl")
			except Exception as e:
				print(f"WARNING: Failed to convert face model: {e}")

			# Convert hair_high.fmdl
			try:
				baseName = os.path.basename(hairModel)[:-6]
				modelFileObj = model2fmdl.loadModel(hairModel)
				outputFmdl = os.path.join(facesFolder, "hair_high.fmdl")
				print(f"converting {baseName}.model to hair_high.fmdl")
				fmdl = model2fmdl.convertModel(modelFileObj, os.path.dirname(hairModel))
				print("saving hair_high.fmdl")
				model2fmdl.saveFmdl(fmdl, outputFmdl)
				convertedFaceFiles.append("hair_high.fmdl")
			except Exception as e:
				print(f"WARNING: Failed to convert hair model: {e}")

		# Always copy face_diff.bin from lib folder
		libFaceDiffBin = os.path.join(os.path.dirname(os.path.realpath(__file__)), "face_diff.bin")
		if os.path.exists(libFaceDiffBin):
			shutil.copy(libFaceDiffBin, os.path.join(facesFolder, "face_diff.bin"))
		else:
			print("WARNING: face_diff.bin not found in lib folder")

		# Create face.fpk.xml
		fpkXml = os.path.join(facesFolder, "face.fpk.xml")
		with open(fpkXml, 'w', encoding='utf-8') as f:
			f.write('<?xml version="1.0"?>\n')
			f.write('<ArchiveFile xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema" xsi:type="FpkFile" Name="face.fpk" FpkType="Fpk">\n')
			f.write('  <Entries>\n')

			# Always include face_diff.bin (from lib folder)
			f.write('    <Entry FilePath="face_diff.bin" />\n')

			# Add all converted face .fmdl files (face_high.fmdl, hair_high.fmdl, etc.)
			for fmdlFilename in convertedFaceFiles:
				f.write(f'    <Entry FilePath="{fmdlFilename}" />\n')

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

		# Use k#### format if sharedBootsFolderName is available, otherwise use playerFolderName
		bootsFolderName = sharedBootsFolderName if sharedBootsFolderName else playerFolderName
		bootsFolder = os.path.join(bootsParentFolder, bootsFolderName)
		if not os.path.exists(bootsFolder):
			os.makedirs(bootsFolder)

		# Combine multiple boots models into a single boots.fmdl
		print(f"Converting {len(bootsModels)} boots model(s) into boots.fmdl")
		try:
			# Get the source directory (directory of first model file)
			sourceDir = os.path.dirname(bootsModels[0]) if len(bootsModels) > 0 else ""

			# Combine all boots models into one FMDL
			combinedFmdl = model2fmdl.combineBootsModels(bootsModels, sourceDir)

			# Save the combined boots.fmdl
			outputFmdl = os.path.join(bootsFolder, "boots.fmdl")
			print("Saving combined boots.fmdl")
			model2fmdl.saveFmdl(combinedFmdl, outputFmdl)
		except Exception as e:
			print(f"WARNING: Failed to convert boots models: {e}")

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
			f.write('    <Entry FilePath="boots.fmdl" />\n')
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

		# Track which glove files were converted (for fpk.xml)
		convertedGloveNames = []

		for modelFile in gloveModels:
			baseName = os.path.basename(modelFile)[:-6]  # Remove .model

			# Determine output name based on suffix
			# Files ending with _l become glove_l.fmdl, files ending with _r become glove_r.fmdl
			if baseName.lower().endswith('_l'):
				outputName = "glove_l"
			elif baseName.lower().endswith('_r'):
				outputName = "glove_r"
			else:
				outputName = baseName

			try:
				modelFileObj = model2fmdl.loadModel(modelFile)
				outputFmdl = os.path.join(glovesFolder, f"{outputName}.fmdl")
				fmdl = model2fmdl.convertModel(modelFileObj, os.path.dirname(modelFile))
				print(f"saving glove model: {baseName}.model -> {outputName}.fmdl")
				model2fmdl.saveFmdl(fmdl, outputFmdl)

				# Track the output name for fpk.xml (avoid duplicates)
				if outputName not in convertedGloveNames:
					convertedGloveNames.append(outputName)
			except Exception as e:
				print(f"WARNING: Failed to convert {modelFile}: {e}")

		# Create glove.fpk.xml
		fpkXml = os.path.join(glovesFolder, "glove.fpk.xml")
		with open(fpkXml, 'w', encoding='utf-8') as f:
			f.write('<?xml version="1.0"?>\n')
			f.write('<ArchiveFile xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema" xsi:type="FpkFile" Name="glove.fpk" FpkType="Fpk">\n')
			f.write('  <Entries>\n')

			# Add all converted glove .fmdl files
			for gloveName in convertedGloveNames:
				f.write(f'    <Entry FilePath="{gloveName}.fmdl" />\n')

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
