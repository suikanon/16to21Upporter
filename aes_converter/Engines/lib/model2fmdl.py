import numpy
import os
import xml.etree.ElementTree as ET
from . import FmdlAntiBlur, FmdlFile, FmdlMeshSplitting, FmdlSplitVertexEncoding
from . import ModelFile, ModelMeshSplitting, ModelSplitVertexEncoding
from . import PesSkeletonData, Skeleton


def convertMeshGeometry(modelMesh, modelFmdlBones):
	"""
	Convert ModelFile mesh geometry to FMDL format.
	ModelFile already has vertices and faces, just need format conversion.
	"""
	fmdlVertices = []
	modelFmdlVertices = {}  # For face conversion

	for modelVertex in modelMesh.vertices:
		fmdlVertex = FmdlFile.FmdlFile.Vertex()

		# Position (already Vector3)
		fmdlVertex.position = modelVertex.position

		# Normal (convert to Vector4)
		if modelMesh.vertexFields.hasNormal:
			fmdlVertex.normal = FmdlFile.FmdlFile.Vector4(
				modelVertex.normal.x,
				modelVertex.normal.y,
				modelVertex.normal.z,
				1.0
			)

		# Tangent (convert to Vector4)
		if modelMesh.vertexFields.hasTangent:
			fmdlVertex.tangent = FmdlFile.FmdlFile.Vector4(
				modelVertex.tangent.x,
				modelVertex.tangent.y,
				modelVertex.tangent.z,
				1.0
			)

		# UV maps (already Vector2 list)
		fmdlVertex.uv = [uv for uv in modelVertex.uv]

		# Color (if present)
		if modelMesh.vertexFields.hasColor:
			fmdlVertex.color = modelVertex.color

		# Bone mapping (convert bone references)
		if modelMesh.vertexFields.hasBoneMapping:
			fmdlVertex.boneMapping = {}

			for (boneIndex, weight) in modelVertex.boneMapping.items():
				# boneIndex is an integer - get the actual bone object from the mesh's bone group
				modelBone = modelMesh.boneGroup.bones[boneIndex]
				# Now use the bone object to look up the corresponding FMDL bone
				fmdlBone = modelFmdlBones[modelBone]
				fmdlVertex.boneMapping[fmdlBone] = weight

		fmdlVertices.append(fmdlVertex)
		modelFmdlVertices[modelVertex] = fmdlVertex

	# Convert faces
	fmdlFaces = []
	for modelFace in modelMesh.faces:
		fmdlFaces.append(FmdlFile.FmdlFile.Face(
			modelFmdlVertices[modelFace.vertices[2]],
			modelFmdlVertices[modelFace.vertices[1]],
			modelFmdlVertices[modelFace.vertices[0]]
		))

	return (fmdlVertices, fmdlFaces)


def convertMesh(modelMesh, modelFmdlBones, materialInstances):
	"""
	Convert a single ModelFile mesh to FMDL mesh.
	"""
	fmdlMesh = FmdlFile.FmdlFile.Mesh()

	# Copy vertex fields
	fmdlMesh.vertexFields = FmdlFile.FmdlFile.VertexFields()
	fmdlMesh.vertexFields.hasNormal = modelMesh.vertexFields.hasNormal
	fmdlMesh.vertexFields.hasTangent = modelMesh.vertexFields.hasTangent
	fmdlMesh.vertexFields.hasBitangent = False
	fmdlMesh.vertexFields.hasColor = modelMesh.vertexFields.hasColor if hasattr(modelMesh.vertexFields, 'hasColor') else False
	fmdlMesh.vertexFields.hasBoneMapping = modelMesh.vertexFields.hasBoneMapping
	fmdlMesh.vertexFields.uvCount = modelMesh.vertexFields.uvCount if hasattr(modelMesh.vertexFields, 'uvCount') else 1
	fmdlMesh.vertexFields.highPrecisionUv = False

	# Convert geometry
	(fmdlMesh.vertices, fmdlMesh.faces) = convertMeshGeometry(modelMesh, modelFmdlBones)

	# Set up bone group
	fmdlMesh.boneGroup = FmdlFile.FmdlFile.BoneGroup()
	if hasattr(modelMesh, 'boneGroup') and modelMesh.boneGroup:
		fmdlMesh.boneGroup.bones = [
			modelFmdlBones[modelBone] for modelBone in modelMesh.boneGroup.bones
		]

	# Find matching material instance
	materialName = modelMesh.material if hasattr(modelMesh, 'material') else None
	fmdlMesh.materialInstance = None
	if materialName:
		for matInstance in materialInstances:
			if matInstance.name == materialName:
				fmdlMesh.materialInstance = matInstance
				break

	# If no material found, use first material or None
	if fmdlMesh.materialInstance is None and len(materialInstances) > 0:
		fmdlMesh.materialInstance = materialInstances[0]

	# Calculate alpha/shadow flags based on material properties
	if fmdlMesh.materialInstance is not None:
		matInst = fmdlMesh.materialInstance

		# Determine if this is a deferred (3DDF) or forward (3DFW) shader
		isDeferred = '3ddf' in matInst.shader.lower()
		isForward = '3dfw' in matInst.shader.lower()

		# Get MTL properties (with defaults if not present)
		twosided = getattr(matInst, 'mtl_twosided', False)
		alphablend = getattr(matInst, 'mtl_alphablend', False)

		# Calculate alphaFlags
		if isDeferred:
			# Deferred Shaders (fox3DDF, pes3DDF)
			# 0 = No Transparency, One Sided
			# 32 = No Transparency, Two Sided
			# 128 = Transparency, One Sided
			# 160 = Transparency, Two Sided
			if alphablend:
				fmdlMesh.alphaFlags = 160 if twosided else 128
			else:
				fmdlMesh.alphaFlags = 32 if twosided else 0

			# Shadow flags for deferred shaders
			# 0 = The mesh has shadows
			# 1 = The mesh doesn't have shadows
			# 2 = Invisible but casts shadow
			# 3 = Invisible and no shadow
			fmdlMesh.shadowFlags = 0  # Enable shadows

		elif isForward:
			# Forward Shaders (fox3DFW, pes3DFW)
			# 16 = Transparency, One Sided
			# 48 = Transparency, Two Sided
			# Forward shaders always have transparency enabled
			fmdlMesh.alphaFlags = 48 if twosided else 16

			# Shadow flags for forward shaders
			# 2 = Invisible but casts shadow
			# 4 = The mesh has shadows
			# 5 = The mesh doesn't have shadows
			fmdlMesh.shadowFlags = 4  # Enable shadows

		else:
			# Unknown shader type, use safe defaults
			fmdlMesh.alphaFlags = 0
			fmdlMesh.shadowFlags = 1

	else:
		# No material instance, use safe defaults
		fmdlMesh.alphaFlags = 0
		fmdlMesh.shadowFlags = 1

	# Calculate bounding box
	if len(fmdlMesh.vertices) > 0:
		fmdlMesh.boundingBox = FmdlFile.FmdlFile.BoundingBox(
			FmdlFile.FmdlFile.Vector4(
				min(v.position.x for v in fmdlMesh.vertices),
				min(v.position.y for v in fmdlMesh.vertices),
				min(v.position.z for v in fmdlMesh.vertices),
				1.0
			),
			FmdlFile.FmdlFile.Vector4(
				max(v.position.x for v in fmdlMesh.vertices),
				max(v.position.y for v in fmdlMesh.vertices),
				max(v.position.z for v in fmdlMesh.vertices),
				1.0
			)
		)
	else:
		fmdlMesh.boundingBox = FmdlFile.FmdlFile.BoundingBox(
			FmdlFile.FmdlFile.Vector4(0, 0, 0, 1.0),
			FmdlFile.FmdlFile.Vector4(0, 0, 0, 1.0),
		)

	# Add extension header for fox3dfw_constant_srgb_ndr_solid shader
	if fmdlMesh.materialInstance is not None:
		shader = fmdlMesh.materialInstance.shader.lower()
		if shader == 'fox3dfw_constant_srgb_ndr_solid':
			fmdlMesh.extensionHeaders.add('Has-Antiblur-Meshes')

	return fmdlMesh


def convertMeshes(model, modelFmdlBones, materialInstances):
	"""Convert all meshes from ModelFile to FMDL format."""
	fmdlMeshes = []
	for modelMesh in model.meshes:
		fmdlMesh = convertMesh(modelMesh, modelFmdlBones, materialInstances)
		fmdlMeshes.append(fmdlMesh)

	return fmdlMeshes


def convertBones(modelBones):
	"""
	Convert bones from ModelFile format to FMDL format.
	Sets up bone hierarchy with parent relationships.
	"""
	bonesToCreate = []
	modelBoneNames = {}

	for modelBone in modelBones:
		boneName = modelBone.name
		if boneName not in bonesToCreate:
			bonesToCreate.append(boneName)
		modelBoneNames[modelBone] = boneName

	fmdlBones = []
	fmdlBonesByName = {}

	for boneName in bonesToCreate:
		fmdlBone = FmdlFile.FmdlFile.Bone()
		fmdlBone.name = boneName
		fmdlBone.children = []

		# Get skeleton data
		if boneName in PesSkeletonData.bones:
			pesBone = PesSkeletonData.bones[boneName]
			numpyMatrix = numpy.linalg.inv(Skeleton.pesToNumpy(pesBone.matrix))
			matrix = [v for row in numpyMatrix for v in row][0:12]

			# Set positions
			(x, y, z) = pesBone.startPosition
			fmdlBone.globalPosition = FmdlFile.FmdlFile.Vector4(x, y, z, 1.0)
			fmdlBone.localPosition = FmdlFile.FmdlFile.Vector4(0.0, 0.0, 0.0, 0.0)
		else:
			matrix = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0]
			fmdlBone.globalPosition = FmdlFile.FmdlFile.Vector4(0.0, 0.0, 0.0, 1.0)
			fmdlBone.localPosition = FmdlFile.FmdlFile.Vector4(0.0, 0.0, 0.0, 0.0)

		fmdlBone.matrix = matrix
		fmdlBone.parent = None
		fmdlBones.append(fmdlBone)
		fmdlBonesByName[boneName] = fmdlBone

	# Set parent relationships
	for fmdlBone in fmdlBones:
		if fmdlBone.name in PesSkeletonData.bones:
			parentName = PesSkeletonData.bones[fmdlBone.name].sklParent
			if parentName and parentName in fmdlBonesByName:
				fmdlBone.parent = fmdlBonesByName[parentName]
				fmdlBone.parent.children.append(fmdlBone)

	return fmdlBones, {modelBone: fmdlBonesByName[name] for modelBone, name in modelBoneNames.items()}


def convertMaterials(model, sourceDirectory, modelType=None, modelCategory=None):
	"""
	Convert materials from ModelFile format to FmdlFile MaterialInstance format.

	Args:
		model: ModelFile object containing materials
		sourceDirectory: Path to directory containing .model file and .mtl files
		modelType: Optional model type from face.xml (e.g., 'uniform', 'face_neck', 'parts')
		modelCategory: Optional model category ('faces', 'boots', 'gloves')

	Returns:
		List of FmdlFile.MaterialInstance objects
	"""
	materialInstances = []

	# Find all .mtl files in the source directory
	mtlFiles = []
	if os.path.isdir(sourceDirectory):
		for filename in os.listdir(sourceDirectory):
			if filename.lower().endswith('.mtl'):
				mtlFiles.append(os.path.join(sourceDirectory, filename))

	# Parse all .mtl files to build a material database
	mtlMaterials = {}  # name -> material XML element
	for mtlFile in mtlFiles:
		try:
			tree = ET.parse(mtlFile)
			root = tree.getroot()

			# Find all <material> elements
			for materialElement in root.findall('material'):
				materialName = materialElement.get('name')
				if materialName:
					mtlMaterials[materialName] = materialElement
		except Exception as e:
			print(f"WARNING: Failed to parse .mtl file {mtlFile}: {e}")

	# Process each material from the ModelFile
	for materialKey in model.materials:
		materialName = model.materials[materialKey]
		materialInstance = FmdlFile.FmdlFile.MaterialInstance()
		materialInstance.name = materialName

		# Check if material exists in .mtl files
		if materialName in mtlMaterials:
			materialElement = mtlMaterials[materialName]
			shader = materialElement.get('shader', '')

			# Assign technique and shader based on shader type
			if shader == 'Basic_C':
				materialInstance.technique = 'fox3DDF_Blin'
				materialInstance.shader = 'fox3ddf_blin'
			elif shader == 'Shadeless':
				materialInstance.technique = 'fox3DFW_ConstantSRGB_NDR_Solid'
				materialInstance.shader = 'fox3dfw_constant_srgb_ndr_solid'
			elif shader == 'Basic_CNSR':
				materialInstance.technique = 'fox3DDF_Blin'
				materialInstance.shader = 'fox3ddf_blin'
			else:
				materialInstance.technique = 'fox3DFW_ConstantSRGB_NDR_Solid'
				materialInstance.shader = 'fox3dfw_constant_srgb_ndr_solid'

			# Extract MTL state properties for alpha/shadow flag calculation
			# Store as custom attributes on the materialInstance
			materialInstance.mtl_twosided = False
			materialInstance.mtl_alphablend = False

			for stateElement in materialElement.findall('state'):
				stateName = stateElement.get('name')
				stateValue = stateElement.get('value', '0')

				if stateName == 'twosided':
					materialInstance.mtl_twosided = (stateValue == '1')
				elif stateName == 'alphablend':
					materialInstance.mtl_alphablend = (stateValue == '1')

			# Find DiffuseMap sampler
			diffuseMapSampler = None
			for samplerElement in materialElement.findall('sampler'):
				if samplerElement.get('name') == 'DiffuseMap':
					diffuseMapSampler = samplerElement
					break

			if diffuseMapSampler is not None:
				texturePath = diffuseMapSampler.get('path', '')

				# Create FmdlTexture object
				texture = FmdlFile.FmdlFile.Texture()

				# Special case: uniform type models use standard uniform texture path
				if modelType and modelType.lower() == 'uniform':
					texture.directory = '/Assets/pes16/model/character/uniform/texture/'
					texture.filename = 'u0123p1.ftex'
				# Check if texture path references Common folder
				elif texturePath.startswith('model/character/uniform/common'):
					# Common folder texture
					texture.directory = '/Assets/pes16/model/character/common/000/sourceimages/'
					texture.filename = os.path.basename(texturePath)
				else:
					# Local texture (path starts with ./ or is just a filename)
					# Extract filename from path (remove ./ prefix if present)
					if texturePath.startswith('./'):
						texturePath = texturePath[2:]

					texture.filename = os.path.basename(texturePath)

					# Determine directory based on model category
					if modelCategory == 'faces':
						texture.directory = '/Assets/pes16/model/character/face/real/00000/sourceimages/'
					elif modelCategory == 'boots':
						texture.directory = '/Assets/pes16/model/character/boots/k0000/'
					elif modelCategory == 'gloves':
						texture.directory = '/Assets/pes16/model/character/glove/g0000/'
					else:
						# Fallback: use old logic based on material name
						if 'face' in materialName.lower() or 'hair' in materialName.lower() or 'oral' in materialName.lower():
							texture.directory = '/Assets/pes16/model/character/face/real/00000/sourceimages/'
						else:
							texture.directory = '/Assets/pes16/model/character/boots/k0000/'

				# Add texture to materialInstance with 'Base_Tex_SRGB' key
				materialInstance.textures = [('Base_Tex_SRGB', texture)]
			else:
				materialInstance.textures = []
		else:
			# Material not found in .mtl file, use default values
			print(f"WARNING: Material '{materialName}' not found in .mtl files, using defaults")
			materialInstance.technique = 'fox3DFW_ConstantSRGB_NDR_Solid'
			materialInstance.shader = 'fox3dfw_constant_srgb_ndr_solid'
			materialInstance.textures = []
			# Default MTL properties
			materialInstance.mtl_twosided = False
			materialInstance.mtl_alphablend = False

		# Parameters field is left empty as per requirements
		materialInstance.parameters = []

		materialInstances.append(materialInstance)

	return materialInstances


def createMeshGroups(model, fmdlMeshes):
	"""
	Create simple mesh groups - one per mesh.
	If ModelFile has mesh group info, use it; otherwise create flat structure.
	"""
	meshGroups = []

	if hasattr(model, 'meshGroups') and model.meshGroups:
		# Use existing mesh groups
		for i, modelMeshGroup in enumerate(model.meshGroups):
			meshGroup = FmdlFile.FmdlFile.MeshGroup()
			meshGroup.name = modelMeshGroup.name if hasattr(modelMeshGroup, 'name') else f"group_{i}"
			meshGroup.visible = True
			meshGroup.parent = None
			meshGroup.children = []
			# Assign meshes based on index (simplified)
			if i < len(fmdlMeshes):
				meshGroup.meshes = [fmdlMeshes[i]]
			else:
				meshGroup.meshes = []
			meshGroups.append(meshGroup)
	else:
		# Create one group per mesh
		for i, mesh in enumerate(fmdlMeshes):
			meshGroup = FmdlFile.FmdlFile.MeshGroup()
			meshGroup.name = f"mesh_{i}"
			meshGroup.visible = True
			meshGroup.parent = None
			meshGroup.children = []
			meshGroup.meshes = [mesh]
			meshGroups.append(meshGroup)

	return meshGroups


def calculateBoneBoundingBoxes(bones, meshes):
	"""Calculate bounding box for each bone based on influenced vertices."""
	boneVertexPositions = {bone: [] for bone in bones}

	for mesh in meshes:
		if not mesh.vertexFields.hasBoneMapping:
			continue

		for vertex in mesh.vertices:
			for bone in vertex.boneMapping:
				boneVertexPositions[bone].append(vertex.position)

	for bone in bones:
		vertexPositions = boneVertexPositions[bone]
		if len(vertexPositions) == 0:
			bone.boundingBox = FmdlFile.FmdlFile.BoundingBox(
				FmdlFile.FmdlFile.Vector4(0.0, 0.0, 0.0, 1.0),
				FmdlFile.FmdlFile.Vector4(0.0, 0.0, 0.0, 1.0)
			)
		else:
			bone.boundingBox = FmdlFile.FmdlFile.BoundingBox(
				FmdlFile.FmdlFile.Vector4(
					min(p.x for p in vertexPositions),
					min(p.y for p in vertexPositions),
					min(p.z for p in vertexPositions),
					1.0
				),
				FmdlFile.FmdlFile.Vector4(
					max(p.x for p in vertexPositions),
					max(p.y for p in vertexPositions),
					max(p.z for p in vertexPositions),
					1.0
				)
			)


def calculateMeshBoundingBox(mesh):
	"""Calculate bounding box from mesh vertices."""
	if len(mesh.vertices) == 0:
		return None

	return FmdlFile.FmdlFile.BoundingBox(
		FmdlFile.FmdlFile.Vector4(
			min(v.position.x for v in mesh.vertices),
			min(v.position.y for v in mesh.vertices),
			min(v.position.z for v in mesh.vertices),
			1.0
		),
		FmdlFile.FmdlFile.Vector4(
			max(v.position.x for v in mesh.vertices),
			max(v.position.y for v in mesh.vertices),
			max(v.position.z for v in mesh.vertices),
			1.0
		)
	)


def calculateMeshGroupBoundingBox(meshGroup):
	"""Recursively calculate mesh group bounding box."""
	boundingBoxes = []

	# Collect from meshes
	for mesh in meshGroup.meshes:
		bbox = calculateMeshBoundingBox(mesh)
		if bbox:
			boundingBoxes.append(bbox)

	# Collect from children
	for child in meshGroup.children:
		bbox = calculateMeshGroupBoundingBox(child)
		if bbox:
			boundingBoxes.append(bbox)

	if len(boundingBoxes) == 0:
		meshGroup.boundingBox = FmdlFile.FmdlFile.BoundingBox(
			FmdlFile.FmdlFile.Vector4(0.0, 0.0, 0.0, 1.0),
			FmdlFile.FmdlFile.Vector4(0.0, 0.0, 0.0, 1.0)
		)
		return None

	meshGroup.boundingBox = FmdlFile.FmdlFile.BoundingBox(
		FmdlFile.FmdlFile.Vector4(
			min(box.min.x for box in boundingBoxes),
			min(box.min.y for box in boundingBoxes),
			min(box.min.z for box in boundingBoxes),
			1.0
		),
		FmdlFile.FmdlFile.Vector4(
			max(box.max.x for box in boundingBoxes),
			max(box.max.y for box in boundingBoxes),
			max(box.max.z for box in boundingBoxes),
			1.0
		)
	)

	return meshGroup.boundingBox


def calculateBoundingBoxes(meshGroups, bones, meshes):
	"""Calculate all bounding boxes."""
	calculateBoneBoundingBoxes(bones, meshes)

	for meshGroup in meshGroups:
		if meshGroup.parent is None:  # Only process root groups
			calculateMeshGroupBoundingBox(meshGroup)


def convertModel(model, sourceDirectory, modelType=None, modelCategory=None):
	"""
	Convert ModelFile to FmdlFile.

	Args:
		model: ModelFile object to convert
		sourceDirectory: Directory containing the model file
		modelType: Optional model type from face.xml (e.g., 'uniform', 'face_neck', 'parts')
		modelCategory: Optional model category ('faces', 'boots', 'gloves')

	Returns:
		FmdlFile object
	"""
	fmdlFile = FmdlFile.FmdlFile()

	# 1. Materials
	materialInstances = convertMaterials(model, sourceDirectory, modelType, modelCategory)
	fmdlFile.materialInstances = materialInstances

	# 2. Bones
	fmdlFile.bones, modelFmdlBones = convertBones(model.bones)

	# 3. Meshes
	fmdlFile.meshes = convertMeshes(model, modelFmdlBones, materialInstances)

	# 4. Mesh Groups
	fmdlFile.meshGroups = createMeshGroups(model, fmdlFile.meshes)

	# 5. Bounding Boxes
	calculateBoundingBoxes(fmdlFile.meshGroups, fmdlFile.bones, fmdlFile.meshes)

	return fmdlFile


def combineBootsModels(modelFiles, sourceDirectory, modelMetadata=None):
	"""
	Combine multiple .model files into a single FMDL file (e.g., for boots).

	This merges all meshes, materials, and mesh groups while deduplicating bones.

	Args:
	    modelFiles: List of .model file paths to combine
	    sourceDirectory: Directory containing the models (for material lookup)
	    modelMetadata: Optional dict mapping modelFile -> {'type': str, 'category': str}

	Returns:
	    Combined FmdlFile object
	"""
	if modelMetadata is None:
		modelMetadata = {}

	if len(modelFiles) == 0:
		# No models to combine, return empty FMDL
		return FmdlFile.FmdlFile()

	if len(modelFiles) == 1:
		# Only one model, just convert it normally
		modelFileObj = loadModel(modelFiles[0])
		# Get metadata for this model
		metadata = modelMetadata.get(modelFiles[0], {})
		# combineBootsModels is always for boots category
		return convertModel(modelFileObj, sourceDirectory,
		                    modelType=metadata.get('type'),
		                    modelCategory=metadata.get('category', 'boots'))

	# Step 1: Load and convert all models to FMDL
	fmdlFiles = []
	for modelFile in modelFiles:
		modelFileObj = loadModel(modelFile)
		# Get metadata for this model
		metadata = modelMetadata.get(modelFile, {})
		# All models in combineBootsModels are boots category
		fmdlFile = convertModel(modelFileObj, os.path.dirname(modelFile),
		                        modelType=metadata.get('type'),
		                        modelCategory=metadata.get('category', 'boots'))
		fmdlFiles.append(fmdlFile)

	# Step 2: Create merged FMDL file
	mergedFmdl = FmdlFile.FmdlFile()

	# Step 3: Merge bones (avoid duplicates by name)
	mergedBones = []
	mergedBonesDict = {}  # boneName → bone object
	boneMappings = []  # List of dicts: oldBone → mergedBone for each model

	for fmdlFile in fmdlFiles:
		boneMapping = {}
		for bone in fmdlFile.bones:
			if bone.name in mergedBonesDict:
				# Bone already exists, reuse it
				boneMapping[bone] = mergedBonesDict[bone.name]
			else:
				# New bone, add to merged list
				mergedBones.append(bone)
				mergedBonesDict[bone.name] = bone
				boneMapping[bone] = bone
		boneMappings.append(boneMapping)

	mergedFmdl.bones = mergedBones

	# Step 4: Merge material instances (keep all)
	mergedFmdl.materialInstances = []
	for fmdlFile in fmdlFiles:
		mergedFmdl.materialInstances.extend(fmdlFile.materialInstances)

	# Step 5: Merge meshes (update bone references)
	mergedFmdl.meshes = []
	for i, fmdlFile in enumerate(fmdlFiles):
		boneMapping = boneMappings[i]
		for mesh in fmdlFile.meshes:
			# Update mesh bone group to reference merged bones
			if hasattr(mesh, 'boneGroup') and mesh.boneGroup and hasattr(mesh.boneGroup, 'bones'):
				mesh.boneGroup.bones = [
					boneMapping[bone] for bone in mesh.boneGroup.bones
				]

			# Update vertex bone mappings
			if mesh.vertexFields.hasBoneMapping:
				for vertex in mesh.vertices:
					if hasattr(vertex, 'boneMapping') and vertex.boneMapping:
						newBoneMapping = {}
						for bone, weight in vertex.boneMapping.items():
							newBoneMapping[boneMapping[bone]] = weight
						vertex.boneMapping = newBoneMapping

			mergedFmdl.meshes.append(mesh)

	# Step 6: Merge mesh groups
	mergedFmdl.meshGroups = []
	for fmdlFile in fmdlFiles:
		mergedFmdl.meshGroups.extend(fmdlFile.meshGroups)

	# Step 7: Recalculate bounding boxes
	calculateBoundingBoxes(mergedFmdl.meshGroups, mergedFmdl.bones, mergedFmdl.meshes)

	return mergedFmdl


def loadModel(filename):
	"""Load a ModelFile from disk."""
	modelFile = ModelFile.readModelFile(filename, ModelFile.ParserSettings())[0]

	modelFile = ModelMeshSplitting.decodeModelSplitMeshes(modelFile)
	modelFile = ModelSplitVertexEncoding.decodeModelVertexLoopPreservation(modelFile)

	return modelFile


def saveFmdl(fmdlFile, filename):
	"""Save an FmdlFile to disk with encoding."""
	fmdlFile = FmdlAntiBlur.encodeFmdlAntiBlur(fmdlFile)
	fmdlFile = FmdlSplitVertexEncoding.encodeFmdlVertexLoopPreservation(fmdlFile)
	fmdlFile = FmdlMeshSplitting.encodeFmdlSplitMeshes(fmdlFile)

	FmdlFile.FmdlFile.writeFile(fmdlFile, filename)
