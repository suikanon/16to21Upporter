import os
import re
import shutil
import struct
import sys
from xml.etree import ElementTree

from .util import ijoin, iglob
from . import model2fmdl, material
from . import FmdlFile, ModelFile


def getTexturesUsedByModel(modelFile):
    """
    Extract list of texture files used by a .model file.

    This function:
    1. Loads the .model file to get material names
    2. Finds corresponding .mtl files in the same directory
    3. Parses the .mtl XML to find texture paths in <sampler> elements
    4. For kit textures, searches the source directory for all matching variants
    5. Returns a set of texture filenames that actually exist and should be copied

    Special handling for kit textures (u0XXX[gp][0-9].dds pattern):
    Kit textures are matched flexibly - any XXX value and any final digit (0-9)
    Example: if .mtl has "number_u0870p0.dds", will match all "number_u0[any]p[0-9].dds" in the folder

    Args:
        modelFile: Path to the .model file

    Returns:
        Set of texture filenames (basenames only, no paths) that exist in source directory
    """
    texturesUsed = set()
    sourceDir = os.path.dirname(modelFile)

    try:
        # Load the model to get material names
        modelFileObj = ModelFile.readModelFile(modelFile, ModelFile.ParserSettings())[0]
        materialNames = list(modelFileObj.materials.values())

        # Find .mtl files in the same directory
        mtlFiles = iglob(sourceDir, "*.mtl")
        for mtlFile in mtlFiles:
            try:
                # Parse the MTL XML
                tree = ElementTree.parse(mtlFile)
                root = tree.getroot()

                # Find all <material> elements with names matching our model's materials
                for materialElement in root.findall('.//material'):
                    materialName = materialElement.get('name')
                    # Skip if this material isn't used by our model
                    if materialName not in materialNames:
                        continue

                    # Extract texture paths from <sampler> elements
                    for samplerElement in materialElement.findall('.//sampler'):
                        texturePath = samplerElement.get('path')
                        if texturePath:
                            # Extract just the filename from the path
                            texturePath = texturePath.replace('\\', '/')
                            textureFilename = os.path.basename(texturePath)

                            # Check for kit texture pattern with optional prefix
                            # Pattern: [optional_prefix_]u0XXX[gp][0-9].dds
                            # Examples: u0879p0.dds, bear_u0879p0.dds, kangaroo_u0879g0.dds
                            kitMatch = re.match(r'(.*?)(u0[0-9a-zA-Z]{3}([gp])[0-9])\.dds', textureFilename,
                                                re.IGNORECASE)
                            if kitMatch:
                                # Extract prefix and type (p or g)
                                prefix = kitMatch.group(1) if kitMatch.group(1) else ''
                                kitType = kitMatch.group(3).lower()  # 'p' or 'g'

                                # Search source directory for all matching kit textures
                                # Pattern: prefix + u0 + any 3 chars + type + any digit + .dds
                                kitPattern = f"{prefix}u0*{kitType}[0-9].dds"
                                matchingTextures = iglob(sourceDir, kitPattern)
                                for texFile in matchingTextures:
                                    texturesUsed.add(os.path.basename(texFile))
                            else:
                                # Regular texture, add as-is
                                texturesUsed.add(textureFilename)

            except Exception as e:
                print(f"WARNING: Failed to parse MTL file {mtlFile}: {e}")
                continue

    except Exception as e:
        print(f"WARNING: Failed to extract textures from {modelFile}: {e}")

    return texturesUsed


def faceDiffFileIsEmpty(faceDiffBin):
    (xScale, yScale, zScale) = struct.unpack('< 3f', faceDiffBin[8:20])
    return xScale < 0.1 and yScale < 0.1 and zScale < 0.1


def buildFmdlMaterials():
    material = FmdlFile.FmdlFile.MaterialInstance()

    return


def parseFaceXml(directory):
    """
    Parse face.xml file to get model type mappings.

    Args:
        directory: Directory to search for face.xml

    Returns:
        Dictionary mapping model filename (lowercase) to type, or None if face.xml not found
    """
    faceXmlPath = ijoin(directory, "face.xml")
    if faceXmlPath is None:
        return None

    try:
        tree = ElementTree.parse(faceXmlPath)
        root = tree.getroot()

        modelTypeMap = {}

        # Find all <model> elements
        for modelElement in root.findall('.//model'):
            modelType = modelElement.get('type')
            modelPath = modelElement.get('path')

            if modelType and modelPath:
                # Extract filename from path (handle wildcards and paths)
                # Path formats: "./face_high_*.model" or "./oral_body.model"
                modelPath = modelPath.replace('\\', '/')
                modelFilename = os.path.basename(modelPath)

                # Handle wildcards - store pattern for matching
                if '*' in modelFilename:
                    # Store the pattern for later matching
                    modelTypeMap[modelFilename.lower()] = modelType
                else:
                    # Exact filename
                    modelTypeMap[modelFilename.lower()] = modelType

        return modelTypeMap

    except Exception as e:
        print(f"WARNING: Failed to parse face.xml in {directory}: {e}")
        return None


def categorizeModelByType(modelType):
    """
    Categorize a model type as 'boots', 'faces', or 'gloves'.

    Args:
        modelType: Type string from face.xml

    Returns:
        'boots', 'faces', 'gloves', or None if unknown
    """
    if not modelType:
        return None

    modelType = modelType.lower()

    # Boots types
    bootsTypes = {'body', 'arm', 'wrist', 'uniform', 'shirt', 'cuff', 'collar', 'boots', 'parts'}
    if modelType in bootsTypes:
        return 'boots'

    # Faces types
    facesTypes = {'face', 'face_neck', 'face_montage', 'eye', 'mouth', 'neck', 'head',
                  'hair', 'hair_cloth', 'edithair'}
    if modelType in facesTypes:
        return 'faces'

    # Gloves types
    glovesTypes = {'handl', 'handr', 'glovel', 'glover'}
    if modelType in glovesTypes:
        return 'gloves'

    return None


def matchModelToType(modelFilename, modelTypeMap):
    """
    Match a model filename to its type using the modelTypeMap.

    Args:
        modelFilename: Basename of the model file (e.g., "oral_body.model")
        modelTypeMap: Dictionary from parseFaceXml

    Returns:
        Model type string, or None if no match
    """
    modelFilename = modelFilename.lower()

    # Try exact match first
    if modelFilename in modelTypeMap:
        return modelTypeMap[modelFilename]

    # Try pattern matching (for wildcards like "face_high_*.model")
    for pattern, modelType in modelTypeMap.items():
        if '*' in pattern:
            # Convert glob pattern to regex
            import fnmatch
            if fnmatch.fnmatch(modelFilename, pattern):
                return modelType

    return None


def convertFaceFolder(sourceDirectories, destinationDirectory, commonDestinationDirectory, bootsSklPath,
                      playerFolderName=None, bootsGlovesBaseId=None, relativePlayerId=None):
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
    hasFaceHighWin32Only = False  # Track if we only have face_high_win32.model (small size)
    hairHighModel = None  # Track face_high_win32.model if size > 990 bytes

    # Dictionary to store model type and category for each model file path
    modelMetadata = {}  # modelFilePath -> {'type': str, 'category': str}

    for directory in sourceDirectories:
        # Try to parse face.xml for model type information
        modelTypeMap = parseFaceXml(directory)
        useFaceXml = modelTypeMap is not None

        if useFaceXml:
            print(f"Using face.xml for model categorization in {directory}")
        else:
            print(f"No face.xml found, using filename-based categorization in {directory}")

        # Find all .model files
        modelFiles = iglob(directory, "*.model")

        for modelFile in modelFiles:
            baseName = os.path.basename(modelFile)[:-6].lower()  # Remove .model extension
            fullBaseName = os.path.basename(modelFile).lower()  # With .model extension

            # Special handling for face_high_win32.model
            if baseName == 'face_high_win32':
                fileSize = os.path.getsize(modelFile)
                if fileSize > 990:
                    print(f"face_high_win32.model is {fileSize} bytes, will convert to hair_high.fmdl")
                    hairHighModel = modelFile
                    modelMetadata[modelFile] = {'type': 'hair', 'category': 'faces'}
                else:
                    print(f"skipping face_high_win32.model ({fileSize} bytes <= 990)")
                continue

            # Determine category and type
            category = None
            modelType = None

            if useFaceXml:
                # Use face.xml for categorization
                modelType = matchModelToType(fullBaseName, modelTypeMap)
                if modelType:
                    category = categorizeModelByType(modelType)
                    if category:
                        print(f"face.xml: {fullBaseName} has type '{modelType}' -> {category}")
                    else:
                        print(f"WARNING: Unknown model type '{modelType}' for {fullBaseName}, using filename fallback")

            # Fallback to filename-based categorization if face.xml didn't provide a category
            if category is None:
                if 'face' in baseName or 'hair' in baseName:
                    category = 'faces'
                elif 'glove' in baseName or 'hand' in baseName:
                    category = 'gloves'
                else:
                    # Everything else goes to boots (parts/uniform)
                    category = 'boots'

            # Store metadata for this model
            modelMetadata[modelFile] = {'type': modelType, 'category': category}

            # Add to appropriate list
            if category == 'faces':
                print(f"adding face: {baseName}")
                faceModels.append(modelFile)
            elif category == 'gloves':
                print(f"adding glove: {baseName}")
                gloveModels.append(modelFile)
            elif category == 'boots':
                print(f"adding boots: {baseName}")
                bootsModels.append(modelFile)

        # Look for face_diff.bin
        faceDiffFile = ijoin(directory, "face_diff.bin")
        if faceDiffFile is not None and faceDiffBinFilename is None:
            faceDiffBinFilename = faceDiffFile

        # Look for portrait
        portraitFile = ijoin(directory, "portrait.dds")
        if portraitFile is not None and portraitFilename is None:
            portraitFilename = portraitFile

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

    # Always create a Faces folder
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
            # Get metadata for this model
            metadata = modelMetadata.get(hairHighModel, {})
            fmdl = model2fmdl.convertModel(modelFileObj, os.path.dirname(hairHighModel),
                                           modelType=metadata.get('type'),
                                           modelCategory=metadata.get('category'))
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
            # Get metadata for this model
            metadata = modelMetadata.get(modelFile, {})
            fmdl = model2fmdl.convertModel(modelFileObj, os.path.dirname(modelFile),
                                           modelType=metadata.get('type'),
                                           modelCategory=metadata.get('category'))
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
            print(
                "WARNING: Ambiguous face models - neither has 'hair' in filename, using smaller file as hair_high.fmdl")
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
            # Get metadata for this model
            metadata = modelMetadata.get(faceModel, {})
            fmdl = model2fmdl.convertModel(modelFileObj, os.path.dirname(faceModel),
                                           modelType=metadata.get('type'),
                                           modelCategory=metadata.get('category'))
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
            # Get metadata for this model
            metadata = modelMetadata.get(hairModel, {})
            fmdl = model2fmdl.convertModel(modelFileObj, os.path.dirname(hairModel),
                                           modelType=metadata.get('type'),
                                           modelCategory=metadata.get('category'))
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
            print(
                "WARNING: Ambiguous face models - neither has 'hair' in filename, using smaller file as hair_high.fmdl")
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
            # Get metadata for this model
            metadata = modelMetadata.get(faceModel, {})
            fmdl = model2fmdl.convertModel(modelFileObj, os.path.dirname(faceModel),
                                           modelType=metadata.get('type'),
                                           modelCategory=metadata.get('category'))
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
            # Get metadata for this model
            metadata = modelMetadata.get(hairModel, {})
            fmdl = model2fmdl.convertModel(modelFileObj, os.path.dirname(hairModel),
                                           modelType=metadata.get('type'),
                                           modelCategory=metadata.get('category'))
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
        f.write(
            '<ArchiveFile xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema" xsi:type="FpkFile" Name="face.fpk" FpkType="Fpk">\n')
        f.write('  <Entries>\n')

        # Always include face_diff.bin (from lib folder)
        f.write('    <Entry FilePath="face_diff.bin" />\n')

        # Add all converted face .fmdl files (face_high.fmdl, hair_high.fmdl, etc.)
        for fmdlFilename in convertedFaceFiles:
            f.write(f'    <Entry FilePath="{fmdlFilename}" />\n')

        f.write('  </Entries>\n')
        f.write('  <References />\n')
        f.write('</ArchiveFile>\n')

    # Collect textures used by face models
    faceTexturesNeeded = set()

    # Get textures from regular face models
    for modelFile in faceModels:
        textures = getTexturesUsedByModel(modelFile)
        faceTexturesNeeded.update(textures)

    # Get textures from hair_high model (large face_high_win32)
    if hairHighModel is not None:
        textures = getTexturesUsedByModel(hairHighModel)
        faceTexturesNeeded.update(textures)

    # Copy only the textures that are actually used
    for directory in sourceDirectories:
        for ext in ['*.dds', '*.ftex']:
            textureFiles = iglob(directory, ext)
            for texFile in textureFiles:
                textureBasename = os.path.basename(texFile)
                # Skip portrait file (handled separately below)
                if 'portrait' in textureBasename.lower():
                    continue
                # Check if this texture is needed by checking both .dds and .ftex extensions
                textureName = textureBasename
                if textureName.lower().endswith('.ftex'):
                    textureName = textureName[:-5] + '.dds'  # Check if .dds version is needed

                if textureName in faceTexturesNeeded or textureBasename in faceTexturesNeeded:
                    destPath = os.path.join(facesFolder, textureBasename)
                    if not os.path.exists(destPath):  # Avoid duplicate copies
                        shutil.copy(texFile, destPath)

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
            combinedFmdl = model2fmdl.combineBootsModels(bootsModels, sourceDir, modelMetadata)

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
            f.write(
                '<ArchiveFile xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema" xsi:type="FpkFile" Name="boots.fpk" FpkType="Fpk">\n')
            f.write('  <Entries>\n')
            f.write('    <Entry FilePath="boots.skl" />\n')
            f.write('    <Entry FilePath="boots.fmdl" />\n')
            f.write('  </Entries>\n')
            f.write('  <References />\n')
            f.write('</ArchiveFile>\n')

        # Collect textures used by boots models
        bootsTexturesNeeded = set()
        for modelFile in bootsModels:
            textures = getTexturesUsedByModel(modelFile)
            bootsTexturesNeeded.update(textures)

        # Copy only the textures that are actually used
        for directory in sourceDirectories:
            for ext in ['*.dds', '*.ftex']:
                textureFiles = iglob(directory, ext)
                for texFile in textureFiles:
                    textureBasename = os.path.basename(texFile)
                    # Skip portrait file
                    if 'portrait' in textureBasename.lower():
                        continue
                    # Check if this texture is needed
                    textureName = textureBasename
                    if textureName.lower().endswith('.ftex'):
                        textureName = textureName[:-5] + '.dds'

                    if textureName in bootsTexturesNeeded or textureBasename in bootsTexturesNeeded:
                        destPath = os.path.join(bootsFolder, textureBasename)
                        if not os.path.exists(destPath):  # Avoid duplicate copies
                            shutil.copy(texFile, destPath)

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
                # Get metadata for this model
                metadata = modelMetadata.get(modelFile, {})
                fmdl = model2fmdl.convertModel(modelFileObj, os.path.dirname(modelFile),
                                               modelType=metadata.get('type'),
                                               modelCategory=metadata.get('category'))
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
            f.write(
                '<ArchiveFile xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema" xsi:type="FpkFile" Name="glove.fpk" FpkType="Fpk">\n')
            f.write('  <Entries>\n')

            # Add all converted glove .fmdl files
            for gloveName in convertedGloveNames:
                f.write(f'    <Entry FilePath="{gloveName}.fmdl" />\n')

            f.write('  </Entries>\n')
            f.write('  <References />\n')
            f.write('</ArchiveFile>\n')

        # Collect textures used by glove models
        glovesTexturesNeeded = set()
        for modelFile in gloveModels:
            textures = getTexturesUsedByModel(modelFile)
            glovesTexturesNeeded.update(textures)

        # Copy only the textures that are actually used
        for directory in sourceDirectories:
            for ext in ['*.dds', '*.ftex']:
                textureFiles = iglob(directory, ext)
                for texFile in textureFiles:
                    textureBasename = os.path.basename(texFile)
                    # Skip portrait file
                    if 'portrait' in textureBasename.lower():
                        continue
                    # Check if this texture is needed
                    textureName = textureBasename
                    if textureName.lower().endswith('.ftex'):
                        textureName = textureName[:-5] + '.dds'

                    if textureName in glovesTexturesNeeded or textureBasename in glovesTexturesNeeded:
                        destPath = os.path.join(glovesFolder, textureBasename)
                        if not os.path.exists(destPath):  # Avoid duplicate copies
                            shutil.copy(texFile, destPath)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: convertFaceFolder <face folder> [boots folder] [gloves folder]")
        sys.exit(1)

    convertFaceFolder(sys.argv[1:], ".", "../../Common")
