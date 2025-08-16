import os
import re
import subprocess
from xml.etree import ElementTree
from PIL import Image

from .util import iglob, ijoin
from . import Ftex

class ModelTexture:
	def __init__(self, path, settings):
		self.path = path
		self.settings = settings
	
	def __eq__(self, other):
		return self.path == other.path and self.settings == other.settings

class ModelMaterial:
	def __init__(self, shader, textures, parameters, stateSettings):
		self.shader = shader
		self.textures = textures
		self.parameters = parameters
		self.stateSettings = stateSettings
	
	def __eq__(self, other):
		return (
			    self.shader == other.shader
			and self.textures == other.textures
			and self.parameters == other.parameters
			and self.stateSettings == other.stateSettings
		)
	
	def __hash__(self):
		return id(self)

def run(command):
	result = subprocess.run(command, capture_output = True, text = True)
	return result.stdout

def convertTextureFile(sourceFilename, destinationDirectory, basename = None):
	if basename is None:
		basename = os.path.basename(sourceFilename)
	pos = basename.rfind('.')
	if pos == -1:
		destinationName = basename
	else:
		destinationName = basename[:pos]
	
	destinationFilename = os.path.join(destinationDirectory, "%s.dds" % destinationName)
	if sourceFilename.lower().endswith('.ftex'):
		Ftex.ftexToDds(sourceFilename, destinationFilename)
	elif sourceFilename.lower().endswith('.dds'):
		open(destinationFilename, 'wb').write(open(sourceFilename, 'rb').read())
	else:
		run(["magick", "convert", sourceFilename, "-format", "dds", "-define", "dds:compression=dxt5", destinationFilename])
	
	identifyData = run(["magick", "identify", "-verbose", destinationFilename])
	
	if "Compression: BC7" in identifyData:
		tempDxt5Filename = os.path.join(destinationDirectory, "%s_temp_dxt5.dds" % destinationName)
		
		run(["magick", "convert", destinationFilename, "-format", "dds", "-define", "dds:compression=dxt5", tempDxt5Filename])
		os.remove(destinationFilename)
		os.rename(tempDxt5Filename, destinationFilename)
	
	dimensions = re.search("Geometry: ([0-9]+)x([0-9]+)\\+.*", identifyData)
	if dimensions is not None:
		width = int(dimensions.group(1))
		height = int(dimensions.group(2))
		if (width & (width - 1)) > 0 or (height & (height - 1)) > 0:
			print("WARNING: Texture '%s' has invalid dimensions %sx%s, this will not work in PES" % (sourceFilename, width, height))
	
	return destinationFilename

def makeUniqueSuffixForFiles(directory, extension, basenamesToMap):
	def filename(basename, suffixIndex):
		if suffixIndex == 0:
			return "%s%s" % (basename, extension)
		else:
			return "%s_%s%s" % (basename, suffixIndex, extension)
	
	suffixIndex = 0
	while True:
		conflictFound = False
		for (basename, sourceFile) in basenamesToMap.items():
			existingFilename = ijoin(directory, filename(basename, suffixIndex))
			if sourceFile is None:
				if existingFilename is not None:
					conflictFound = True
					break
			else:
				if existingFilename is not None:
					existingContent = open(existingFilename, 'rb').read()
					newContent = open(sourceFile, 'rb').read()
					if existingContent != newContent:
						conflictFound = True
						break
		
		if not conflictFound:
			break
		suffixIndex += 1
	
	finalFilenames = {}
	for (basename, sourceFile) in basenamesToMap.items():
		existingFilename = ijoin(directory, filename(basename, suffixIndex))
		if existingFilename is not None:
			os.remove(sourceFile)
		else:
			os.rename(sourceFile, os.path.join(directory, filename(basename, suffixIndex)))
		finalFilenames[basename] = filename(basename, suffixIndex)
	
	if suffixIndex == 0:
		return ""
	else:
		return "_%s" % suffixIndex

def convertTexture(sourceDirectory, filename, putInCommonDirectory, faceDirectory, commonDirectory):
	def findSourceTexture(basename):
		ddsFilename = ijoin(sourceDirectory, basename + ".dds")
		if ddsFilename is not None:
			return ddsFilename
		ftexFilename = ijoin(sourceDirectory, basename + ".ftex")
		if ftexFilename is not None:
			return ftexFilename
		ftexFilename = ijoin(sourceDirectory, basename + ".png")
		if ftexFilename is not None:
			return ftexFilename
		return None
	
	if putInCommonDirectory:
		destinationDirectory = commonDirectory
		prefix = "model/character/uniform/common/XXX/"
	else:
		destinationDirectory = faceDirectory
		prefix = "./"
	
	basename = os.path.basename(filename)
	pos = basename.rfind('.')
	if pos == -1:
		name = basename
	else:
		name = basename[:pos]
	
	if re.search("u0[0-9a-zA-Z]{3}[gp]0", name) is not None:
		tempFilenames = {}
		
		for i in range(1, 10):
			kitFilename = re.sub("(u0[0-9a-zA-Z]{3}[pg])0", "\\g<1>%s" % i, name)
			kitTexture = findSourceTexture(kitFilename)
			
			if kitTexture is not None:
				tempFilename = "temp19to16_%s.dds" % kitFilename
				convertTextureFile(kitTexture, destinationDirectory, tempFilename)
				tempFilenames[kitFilename] = ijoin(destinationDirectory, tempFilename)
		
		suffix = makeUniqueSuffixForFiles(destinationDirectory, ".dds", tempFilenames)
		if len(tempFilenames) == 0:
			finalTextureFilename = None
		else:
			finalTextureFilename = "%s%s.dds" % (list(tempFilenames.keys())[0], suffix)
		
		return (os.path.join(destinationDirectory, finalTextureFilename), prefix + "%s%s.dds" % (name, suffix))
	else:
		sourceTexture = findSourceTexture(name)
		if sourceTexture is None:
			return (None, None)
		
		tempFilename = "temp19to16_%s.dds" % name
		convertTextureFile(sourceTexture, destinationDirectory, tempFilename)
		
		suffix = makeUniqueSuffixForFiles(destinationDirectory, ".dds", { name : ijoin(destinationDirectory, tempFilename) })
		finalFilename = "%s%s.dds" % (name, suffix)
		
		return (os.path.join(destinationDirectory, finalFilename), prefix + finalFilename)

#
# Given an fmdl texture object and a directory containing the surrounding fmdl file,
# find a source texture file for it and convert it to a destination texture.
# Returns (the output texture filename, the .mtl texture path relative to the destination directory).
#
def findTexture(fmdlTexture, sourceDirectory, faceDirectory, commonDirectory):
	def findModelDirectory(parentDirectories, globPattern):
		for parentDirectory in parentDirectories:
			if parentDirectory is not None:
				entries = iglob(parentDirectory, globPattern)
				if len(entries) > 0:
					return entries
		return []
	
	texturePathComponents = [component for component in (fmdlTexture.directory + '/' + fmdlTexture.filename).replace('\\', '/').split('/') if len(component) > 0]
	
	#
	# Try to find the texture in $sourceDirectory if the sourceDirectory model type (face, boots, gloves) matches the texture model type
	#
	if os.path.basename(sourceDirectory).lower()[0] == 'k':
		# boots/k0000/something.dds
		if texturePathComponents[-3].lower() == 'boots':
			return convertTexture(sourceDirectory, texturePathComponents[-1], False, faceDirectory, commonDirectory)
	elif os.path.basename(sourceDirectory).lower()[0] == 'g':
		# glove/g0000/something.dds
		if texturePathComponents[-3].lower() == 'glove':
			return convertTexture(sourceDirectory, texturePathComponents[-1], False, faceDirectory, commonDirectory)
	else:
		# face/real/00000/sourceimages/something.dds
		if texturePathComponents[-5].lower() == 'face' and texturePathComponents[-4].lower() == 'real':
			return convertTexture(sourceDirectory, texturePathComponents[-1], False, faceDirectory, commonDirectory)
	
	#
	# Fail to find global common textures
	# common/sourceimages/something.dds
	#
	if texturePathComponents[-3].lower() == 'common' and texturePathComponents[-2].lower() == 'sourceimages':
		return (None, None)
	
	#
	# If none of these applies, assume the grandparent of $sourceDirectory is an export directory and work from there.
	#
	parentDirectory = os.path.dirname(sourceDirectory)
	grandparentDirectory = os.path.dirname(parentDirectory)
	isCommonDirectory = False
	if texturePathComponents[-3].lower() == 'boots':
		# boots/k0000/something.dds
		bootsId = texturePathComponents[-2][1:5]
		bootFolders = findModelDirectory([ijoin(grandparentDirectory, "Boots"), parentDirectory], "k%s*" % bootsId)
		if len(bootFolders) == 0:
			textureDirectory = None
		else:
			if len(bootFolders) > 1:
				print("WARNING: Mapping texture '%s/%s': found multiple conflicting boots folders for boots '%s'" % (fmdlTexture.directory, fmdlTexture.filename, bootsId))
			textureDirectory = bootFolders[0]
	elif texturePathComponents[-3].lower() == 'glove':
		# glove/g0000/something.dds
		glovesId = texturePathComponents[-2][1:5]
		gloveFolders = findModelDirectory([ijoin(grandparentDirectory, "Gloves"), parentDirectory], "g%s*" % glovesId)
		if len(gloveFolders) == 0:
			textureDirectory = None
		else:
			if len(gloveFolders) > 1:
				print("WARNING: Mapping texture '%s/%s': found multiple conflicting gloves folders for gloves '%s'" % (fmdlTexture.directory, fmdlTexture.filename, glovesId))
			textureDirectory = gloveFolders[0]
	elif texturePathComponents[-5].lower() == 'face' and texturePathComponents[-4].lower() == 'real':
		# face/real/00000/sourceimages/something.dds
		relativePlayerId = texturePathComponents[-3][3:5]
		faceFolders = findModelDirectory([ijoin(grandparentDirectory, "Faces"), parentDirectory], "???%s*" % relativePlayerId)
		if len(faceFolders) == 0:
			textureDirectory = None
		else:
			if len(faceFolders) > 1:
				print("WARNING: Mapping texture '%s/%s': found multiple conflicting face folders for player '%s'" % (fmdlTexture.directory, fmdlTexture.filename, relativePlayerId))
			textureDirectory = faceFolders[0]
	elif texturePathComponents[-4].lower() == 'common':
		# common/000/sourceimages/something.dds
		
		if texturePathComponents[-1].lower().startswith('dummy_kit'):
			return (None, "model/character/uniform/common/XXX/dummy_kit.dds")
		if texturePathComponents[-1].lower().startswith('dummy_gk_kit'):
			return (None, "model/character/uniform/common/XXX/dummy_gk_kit.dds")
		
		commonFolders = findModelDirectory([grandparentDirectory, parentDirectory], "Common")
		if len(commonFolders) == 0:
			textureDirectory = None
		else:
			textureDirectory = commonFolders[0]
		isCommonDirectory = True
	else:
		textureDirectory = None
	
	if textureDirectory is None:
		return (None, None)
	
	return convertTexture(textureDirectory, texturePathComponents[-1], isCommonDirectory, faceDirectory, commonDirectory)

def findTextureForRole(fmdlMaterialInstance, roles):
	for (role, fmdlTexture) in fmdlMaterialInstance.textures:
		if role in roles:
			return fmdlTexture
	return None

def textureUsesAlphaBlending(texturePath):
	image = Image.open(texturePath)
	if image.mode != 'RGBA':
		return False
	alphaHistogram = image.getchannel('A').histogram()
	zeroCount = 0
	oneCount = 0
	blendCount = 0
	for alpha, pixelCount in zip(range(len(alphaHistogram)), alphaHistogram):
		if alpha < 16:
			zeroCount += pixelCount
		elif alpha > 240:
			oneCount += pixelCount
		else:
			blendCount += pixelCount
	
	#
	# Consider an image to use alpha blending if more than 10% of the non-hidden pixels
	# are non-opaque.
	#
	return (blendCount * 10) > (blendCount + oneCount)

def buildDecalMaterial(mesh, sourceDirectory, faceDirectory, commonDirectory):
	# if primary texture is present, map to Basic_C with alpha blending enabled.
	# if primary texture is missing, delete.
	
	fmdlBaseTexture = findTextureForRole(mesh.materialInstance, ['Base_Tex_SRGB', 'Base_Tex_LIN'])
	if fmdlBaseTexture is None:
		return None
	(baseTextureRealFilename, baseTexturePath) = findTexture(fmdlBaseTexture, sourceDirectory, faceDirectory, commonDirectory)
	if baseTexturePath is None:
		return None
	
	return ModelMaterial(
		"Overlay",
		{
			"DiffuseMap": ModelTexture(baseTexturePath, {
				"srgb": 1,
				"minfilter": "linear",
				"maxfilter": "linear",
				"magfilter": "linear",
			}),
		},
		{},
		{
			"ztest": 1,
			"zwrite": 0,
			"twosided": 1 if mesh.alphaFlags & 32 > 0 else 0,
			"alphatest": 0,
			"alpharef": 0,
			"alphablend": 1,
			"blendmode": 0,
		},
	)

def buildMetalMaterial(mesh, baseTexturePath, sourceDirectory, faceDirectory, commonDirectory):
	#
	# Build an all-grey RoughnessMap
	#
	roughnessImage = Image.new('RGBA', (4, 4), (128, 128, 128, 255))
	roughnessImageFilename = os.path.join(commonDirectory, "metal_roughness.png")
	roughnessImage.save(roughnessImageFilename)
	
	(roughnessTextureRealFilename, roughnessTexturePath) = convertTexture(commonDirectory, "metal_roughness.png", True, faceDirectory, commonDirectory)
	os.remove(roughnessImageFilename)
	
	return ModelMaterial(
		"Basic_CNSR",
		{
			"DiffuseMap": ModelTexture(baseTexturePath, {
				"srgb": 1,
				"minfilter": "linear",
				"magfilter": "linear",
			}),
			"SpecularMap": ModelTexture(baseTexturePath, {
				"srgb": 1,
				"minfilter": "linear",
				"magfilter": "linear",
			}),
			"RoughnessMap": ModelTexture(roughnessTexturePath, {
				"srgb": 0,
				"minfilter": "linear",
				"magfilter": "linear",
			}),
		},
		{
			"Reflection": (1.0, 1.0, 1.0, 0.0),
			"Shininess":  (0.9, 0.0, 0.0, 1.0),
		},
		{
			"ztest": 1,
			"zwrite": 1,
			"twosided": 1 if mesh.alphaFlags & 32 > 0 else 0,
			"alphatest": 1,
			"alpharef": 0,
			"alphablend": 0,
			"blendmode": 0,
		},
	)

def buildOpaqueBlinMaterial(mesh, baseTexturePath, sourceDirectory, faceDirectory, commonDirectory):
	return ModelMaterial(
		"Basic_C",
		{
			"DiffuseMap": ModelTexture(baseTexturePath, {
				"srgb": 1,
				"minfilter": "linear",
				"magfilter": "linear",
			}),
		},
		{},
		{
			"ztest": 1,
			"zwrite": 1,
			"twosided": 1 if mesh.alphaFlags & 32 > 0 else 0,
			"alphatest": 1,
			"alpharef": 0,
			"alphablend": 0,
			"blendmode": 0,
		},
	)

def buildTransparentBlinMaterial(mesh, baseTexturePath, sourceDirectory, faceDirectory, commonDirectory):
	return ModelMaterial(
		"Basic_C",
		{
			"DiffuseMap": ModelTexture(baseTexturePath, {
				"srgb": 1,
				"minfilter": "linear",
				"magfilter": "linear",
			}),
		},
		{},
		{
			"ztest": 1,
			"zwrite": 0,
			"twosided": 1 if mesh.alphaFlags & 32 > 0 else 0,
			"alphatest": 0,
			"alpharef": 0,
			"alphablend": 1,
			"blendmode": 0,
		},
	)

def buildBlinMaterial(mesh, baseTexturePath, sourceDirectory, faceDirectory, commonDirectory, baseTextureRealFilename):
	if 'has-antiblur-meshes' in mesh.extensionHeaders:
		transparent = False
	elif baseTextureRealFilename is None:
		transparent = False
	else:
		transparent = textureUsesAlphaBlending(baseTextureRealFilename)
	
	if transparent:
		return buildTransparentBlinMaterial(mesh, baseTexturePath, sourceDirectory, faceDirectory, commonDirectory)
	else:
		return buildOpaqueBlinMaterial(mesh, baseTexturePath, sourceDirectory, faceDirectory, commonDirectory)

def buildConstantMaterial(mesh, baseTexturePath, sourceDirectory, faceDirectory, commonDirectory, baseTextureRealFilename):
	srgb = "srgb" in mesh.materialInstance.shader or "forward" not in mesh.materialInstance.shader
	
	if 'has-antiblur-meshes' in mesh.extensionHeaders:
		transparent = False
	elif baseTextureRealFilename is None:
		transparent = False
	else:
		transparent = textureUsesAlphaBlending(baseTextureRealFilename)
	
	return ModelMaterial(
		"Shadeless",
		{
			"DiffuseMap": ModelTexture(baseTexturePath, {
				"srgb": 1 if srgb else 0,
				"minfilter": "linear",
				"magfilter": "linear",
			}),
		},
		{},
		{
			"ztest": 1,
			"zwrite": 0 if transparent else 1,
			"twosided": 1 if mesh.alphaFlags & 32 > 0 else 0,
			"alphatest": 0 if transparent else 1,
			"alpharef": 0,
			"alphablend": 1 if transparent else 0,
			"blendmode": 0,
		},
	)

def buildMaterial(mesh, fmdlFilename, sourceDirectory, faceDirectory, commonDirectory):
	shader = mesh.materialInstance.shader
	
	if len(mesh.faces) <= 1:
		return None
	
	if "fuzzblock" in shader:
		return None
	if "3ddc" in shader or "eyeocclusion" in shader or "translucent" in shader:
		return buildDecalMaterial(mesh, sourceDirectory, faceDirectory, commonDirectory)
	
	fmdlBaseTexture = findTextureForRole(mesh.materialInstance, ['Base_Tex_SRGB', 'Base_Tex_LIN'])
	if fmdlBaseTexture is None:
		print("WARNING: missing base texture for material '%s' in fmdl file '%s'" % (mesh.materialInstance.name, fmdlFilename))
		baseTexturePath = "./.dds"
		baseTextureRealFilename = None
	else:
		(baseTextureRealFilename, baseTexturePath) = findTexture(fmdlBaseTexture, sourceDirectory, faceDirectory, commonDirectory)
		if baseTexturePath is None:
			print("WARNING: missing texture '%s' for fmdl file '%s'" % (fmdlBaseTexture.filename, fmdlFilename))
			baseTexturePath = "./.dds"
	
	if "ggx" in shader:
		return buildMetalMaterial(mesh, baseTexturePath, sourceDirectory, faceDirectory, commonDirectory)
	if "glass" in shader:
		# TODO: Build fancier glass material if this ever comes up
		return buildTransparentBlinMaterial(mesh, baseTexturePath, sourceDirectory, faceDirectory, commonDirectory)
	if "hair" in shader:
		return buildBlinMaterial(mesh, baseTexturePath, sourceDirectory, faceDirectory, commonDirectory, baseTextureRealFilename)
	if "3ddf" in shader or "blin" in shader:
		return buildOpaqueBlinMaterial(mesh, baseTexturePath, sourceDirectory, faceDirectory, commonDirectory)
	if "constant" in shader or "lambert" in shader:
		return buildConstantMaterial(mesh, baseTexturePath, sourceDirectory, faceDirectory, commonDirectory, baseTextureRealFilename)
	if "3dfw" in shader:
		print("WARNING: unknown shader '%s' for fmdl file '%s', using constant shader" % (shader, fmdlFilename))
		return buildConstantMaterial(mesh, baseTexturePath, sourceDirectory, faceDirectory, commonDirectory, baseTextureRealFilename)
	if True:
		print("WARNING: unknown shader '%s' for fmdl file '%s', using dummy material" % (shader, fmdlFilename))
		return ""

def buildMaterialsXml(materialNames):
	materialsElement = ElementTree.Element('materialset')
	for material, name in materialNames.items():
		materialElement = ElementTree.Element('material', { 'name': name, 'shader': material.shader })
		
		for role, texture in material.textures.items():
			textureElement = ElementTree.Element('sampler', {
				'name': role,
				'path': texture.path,
				**{ key: str(value) for (key, value) in texture.settings.items()},
			})
			materialElement.append(textureElement)
		
		for role, values in material.parameters.items():
			valueAttributes = {}
			if len(values) > 0:
				valueAttributes['x'] = str(values[0])
			if len(values) > 1:
				valueAttributes['y'] = str(values[1])
			if len(values) > 2:
				valueAttributes['z'] = str(values[2])
			if len(values) > 3:
				valueAttributes['w'] = str(values[3])
			parameterElement = ElementTree.Element('vector', {
				'name': role,
				**valueAttributes,
			})
			materialElement.append(parameterElement)
		
		stateOrder = ["ztest", "zwrite", "twosided", "alphatest", "alpharef", "alphablend", "blendmode"]
		stateSettingKeys = sorted(material.stateSettings.keys(), key = lambda x : stateOrder.index(x) if x in stateOrder else x)
		for stateSetting in stateSettingKeys:
			settingElement = ElementTree.Element('state', {
				'name': stateSetting,
				'value': str(material.stateSettings[stateSetting])
			})
			materialElement.append(settingElement)
		
		materialsElement.append(materialElement)
	
	ElementTree.indent(materialsElement)
	
	return ElementTree.tostring(materialsElement, encoding = 'utf-8')

def buildMaterials(fmdls, destinationDirectory, commonDestinationDirectory):
	class MaterialSource:
		def __init__(self, mesh, fmdlFilename):
			self.mesh = mesh
			self.fmdlFilename = fmdlFilename
	
	meshMaterials = {}
	materialSources = {}
	
	#
	# Build a ModelMaterial for each mesh
	#
	for (fmdlFilename, fmdlDirectory, fmdl) in fmdls:
		for mesh in fmdl.meshes:
			material = buildMaterial(mesh, fmdlFilename, fmdlDirectory, destinationDirectory, commonDestinationDirectory)
			meshMaterials[mesh] = material
			materialSources[material] = MaterialSource(mesh, fmdlFilename)
	
	#
	# Determine unique materials
	#
	equivalentMaterials = {}
	uniqueMaterials = []
	for material in meshMaterials.values():
		if type(material) == str or material is None:
			continue
		found = False
		for existingMaterial in uniqueMaterials:
			if material == existingMaterial:
				equivalentMaterials[material] = existingMaterial
				found = True
				break
		if not found:
			uniqueMaterials.append(material)
	
	#
	# Make a material name for each unique ModelMaterial
	#
	nameMaterials = {}
	for material in uniqueMaterials:
		name = materialSources[material].mesh.materialInstance.name
		if name not in nameMaterials:
			nameMaterials[name] = []
		nameMaterials[name].append(material)
	
	def fmdlNamePrefix(materialSource):
		basename = os.path.basename(materialSource.fmdlFilename)
		if '.' in basename:
			basename = basename[:basename.find('.')]
		return basename.lower()
	
	def twosidedNameSuffix(materialSource):
		if materialSource.mesh.alphaFlags & 32 > 0:
			return "twosided"
		else:
			return "onesided"
	
	materialNames = {}
	for name, materials in nameMaterials.items():
		if len(materials) == 1:
			materialNames[materials[0]] = name
			continue
		
		materialsByPrefix = {}
		for material in materials:
			prefix = fmdlNamePrefix(materialSources[material])
			if prefix not in materialsByPrefix:
				materialsByPrefix[prefix] = []
			materialsByPrefix[prefix].append(material)
		
		for prefix, prefixedMaterials in materialsByPrefix.items():
			if len(prefixedMaterials) == 1:
				materialNames[prefixedMaterials[0]] = "%s_%s" % (prefix, name)
				continue
			
			materialsBySuffix = {}
			for material in prefixedMaterials:
				suffix = twosidedNameSuffix(materialSources[material])
				if suffix not in materialsBySuffix:
					materialsBySuffix[suffix] = []
				materialsBySuffix[suffix].append(material)
			
			for suffix, suffixedMaterials in materialsBySuffix.items():
				if len(suffixedMaterials) == 1:
					materialNames[suffixedMaterials[0]] = "%s_%s_%s" % (prefix, name, suffix)
					continue
				
				for i in range(len(suffixedMaterials)):
					materialNames[suffixedMaterials[i]] = "%s_%s_%s_%s" % (prefix, name, suffix, i + 1)
	
	#
	# Make a material xml node for each unique material
	#
	materialsFile = buildMaterialsXml(materialNames)
	
	#
	# For each mesh, find the name of the material to use for it
	#
	meshMaterialNames = {}
	for mesh, material in meshMaterials.items():
		if material is None:
			continue
		
		if type(material) == str:
			materialName = material
		else:
			if material in equivalentMaterials:
				equivalentMaterial = equivalentMaterials[material]
			else:
				equivalentMaterial = material
			materialName = materialNames[equivalentMaterial]
		
		meshMaterialNames[mesh] = materialName
	
	return (materialsFile, meshMaterialNames)
