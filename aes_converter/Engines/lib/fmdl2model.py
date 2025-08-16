import numpy
from . import FmdlAntiBlur, FmdlFile, FmdlMeshSplitting, FmdlSplitVertexEncoding
from . import ModelFile, ModelMeshSplitting, ModelSplitVertexEncoding
from . import PesSkeletonData, Skeleton

missingBones = {
	'dsk_belly_ba_l': 'sk_belly',
	'dsk_belly_ba_r': 'sk_belly',
	'dsk_belly_f_l': 'sk_belly',
	'dsk_belly_f_r': 'sk_belly',
	'dsk_belly_o_l': 'sk_belly',
	'dsk_belly_o_r': 'sk_belly',
	'dsk_hip_l': 'sk_thigh_l',
	'dsk_hip_r': 'sk_thigh_r',
	'dsk_leg_l': 'sk_leg_l',
	'dsk_leg_r': 'sk_leg_r',
	'dsk_pants_l': 'sk_thigh_l',
	'dsk_pants_r': 'sk_thigh_r',
	'dsk_thigh_l': 'sk_thigh_l',
	'dsk_thigh_r': 'sk_thigh_r',
	'dsk_upperarm_skin_l': 'dsk_upperarm_l',
	'dsk_upperarm_skin_r': 'dsk_upperarm_r',
	'dsk_upperarm_skin_t_l': 'dsk_upperarm_l',
	'dsk_upperarm_skin_t_r': 'dsk_upperarm_r',
}

def convertBones(fmdlBones):
	bonesToCreate = []
	fmdlBoneNames = {}
	for fmdlBone in fmdlBones:
		boneName = fmdlBone.name
		if boneName in missingBones:
			boneName = missingBones[boneName]
		if boneName not in bonesToCreate:
			bonesToCreate.append(boneName)
		fmdlBoneNames[fmdlBone] = boneName
	
	modelBones = []
	modelBonesByName = {}
	for boneName in bonesToCreate:
		if boneName in PesSkeletonData.bones:
			numpyMatrix = numpy.linalg.inv(Skeleton.pesToNumpy(PesSkeletonData.bones[boneName].matrix))
			matrix = [v for row in numpyMatrix for v in row][0:12]
		else:
			matrix = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0]
		
		modelBone = ModelFile.ModelFile.Bone(boneName, matrix)
		modelBones.append(modelBone)
		modelBonesByName[boneName] = modelBone
	
	return modelBones, { fmdlBone : modelBonesByName[name] for fmdlBone, name in fmdlBoneNames.items() }

def convertMesh(fmdlMesh, fmdlModelBones):
	modelMesh = ModelFile.ModelFile.Mesh()
	
	modelMesh.boneGroup = ModelFile.ModelFile.BoneGroup()
	fmdlBoneIndices = {}
	for fmdlBone in fmdlMesh.boneGroup.bones:
		modelBone = fmdlModelBones[fmdlBone]
		if modelBone not in modelMesh.boneGroup.bones:
			modelMesh.boneGroup.bones.append(modelBone)
		fmdlBoneIndices[fmdlBone] = modelMesh.boneGroup.bones.index(modelBone)
	
	modelMesh.vertexFields = ModelFile.ModelFile.VertexFields()
	modelMesh.vertexFields.hasNormal = fmdlMesh.vertexFields.hasNormal
	modelMesh.vertexFields.hasTangent = fmdlMesh.vertexFields.hasTangent
	modelMesh.vertexFields.hasBitangent = False
	modelMesh.vertexFields.hasColor = False
	modelMesh.vertexFields.hasBoneMapping = fmdlMesh.vertexFields.hasBoneMapping
	uvMapsToInclude = []
	for i in range(fmdlMesh.vertexFields.uvCount):
		#if i not in fmdlMesh.vertexFields.uvEqualities or fmdlMesh.vertexFields.uvEqualities[i] >= i:
		uvMapsToInclude.append(i)
		modelMesh.vertexFields.uvCount += 1
	
	fmdlModelPositions = {}
	fmdlModelVertices = {}
	modelMesh.vertices = []
	for fmdlVertex in fmdlMesh.vertices:
		modelVertex = ModelFile.ModelFile.Vertex()
		
		if fmdlVertex.position in fmdlModelPositions:
			modelVertex.position = fmdlModelPositions[fmdlVertex.position]
		else:
			modelVertex.position = ModelFile.ModelFile.Vector3(fmdlVertex.position.x, fmdlVertex.position.y, fmdlVertex.position.z)
			fmdlModelPositions[fmdlVertex.position] = modelVertex.position
		
		if modelMesh.vertexFields.hasNormal:
			modelVertex.normal = ModelFile.ModelFile.Vector3(fmdlVertex.normal.x, fmdlVertex.normal.y, fmdlVertex.normal.z)
		if modelMesh.vertexFields.hasTangent:
			modelVertex.tangent = ModelFile.ModelFile.Vector3(fmdlVertex.tangent.x, fmdlVertex.tangent.y, fmdlVertex.tangent.z)
		
		for uvMap in uvMapsToInclude:
			modelVertex.uv.append(ModelFile.ModelFile.Vector2(fmdlVertex.uv[uvMap].u, fmdlVertex.uv[uvMap].v))
		
		if modelMesh.vertexFields.hasBoneMapping:
			modelVertex.boneMapping = {}
			for (bone, weight) in fmdlVertex.boneMapping.items():
				boneIndex = fmdlBoneIndices[bone]
				if boneIndex not in modelVertex.boneMapping:
					modelVertex.boneMapping[boneIndex] = 0
				modelVertex.boneMapping[boneIndex] += weight
		
		modelMesh.vertices.append(modelVertex)
		fmdlModelVertices[fmdlVertex] = modelVertex
	
	modelMesh.faces = []
	for fmdlFace in fmdlMesh.faces:
		modelMesh.faces.append(ModelFile.ModelFile.Face(*reversed([fmdlModelVertices[fmdlVertex] for fmdlVertex in fmdlFace.vertices])))
	
	if len(modelMesh.vertices) == 0:
		modelMesh.boundingBox = ModelFile.ModelFile.BoundingBox(
			ModelFile.ModelFile.Vector3(0, 0, 0),
			ModelFile.ModelFile.Vector3(0, 0, 0),
		)
	else:
		modelMesh.boundingBox = ModelFile.ModelFile.BoundingBox(
			ModelFile.ModelFile.Vector3(
				min(vertex.position.x for vertex in modelMesh.vertices),
				min(vertex.position.y for vertex in modelMesh.vertices),
				min(vertex.position.z for vertex in modelMesh.vertices),
			),
			ModelFile.ModelFile.Vector3(
				max(vertex.position.x for vertex in modelMesh.vertices),
				max(vertex.position.y for vertex in modelMesh.vertices),
				max(vertex.position.z for vertex in modelMesh.vertices),
			),
		)
	
	return modelMesh

def convertMeshes(fmdl, fmdlMeshMaterialNames, fmdlModelBones):
	modelMeshes = []
	for fmdlMesh in fmdl.meshes:
		if fmdlMesh not in fmdlMeshMaterialNames:
			continue
		
		modelMesh = convertMesh(fmdlMesh, fmdlModelBones)
		modelMesh.material = fmdlMeshMaterialNames[fmdlMesh]
		
		for fmdlMeshGroup in fmdl.meshGroups:
			if fmdlMesh in fmdlMeshGroup.meshes:
				modelMesh.name = fmdlMeshGroup.name
		
		modelMeshes.append(modelMesh)
	
	return modelMeshes

def convertFmdl(fmdl, fmdlMeshMaterialNames):
	modelFile = ModelFile.ModelFile()
	modelFile.bones, fmdlModelBones = convertBones(fmdl.bones)
	modelFile.meshes = convertMeshes(fmdl, fmdlMeshMaterialNames, fmdlModelBones)
	
	if len(modelFile.meshes) == 0:
		modelFile.boundingBox = ModelFile.ModelFile.BoundingBox(
			ModelFile.ModelFile.Vector3(0, 0, 0),
			ModelFile.ModelFile.Vector3(0, 0, 0),
		)
	else:
		modelFile.boundingBox = ModelFile.ModelFile.BoundingBox(
			ModelFile.ModelFile.Vector3(
				min(mesh.boundingBox.min.x for mesh in modelFile.meshes),
				min(mesh.boundingBox.min.y for mesh in modelFile.meshes),
				min(mesh.boundingBox.min.z for mesh in modelFile.meshes),
			),
			ModelFile.ModelFile.Vector3(
				max(mesh.boundingBox.max.x for mesh in modelFile.meshes),
				max(mesh.boundingBox.max.y for mesh in modelFile.meshes),
				max(mesh.boundingBox.max.z for mesh in modelFile.meshes),
			),
		)
	
	materials = set()
	for modelMesh in modelFile.meshes:
		materials.add(modelMesh.material)
	modelFile.materials = list(materials)
	
	modelFile.extensionHeaders.add('Skeleton-Type: Simplified')
	
	return modelFile

def loadFmdl(filename):
	fmdlFile = FmdlFile.FmdlFile()
	fmdlFile.readFile(filename)
	
	fmdlFile = FmdlMeshSplitting.decodeFmdlSplitMeshes(fmdlFile)
	fmdlFile = FmdlSplitVertexEncoding.decodeFmdlVertexLoopPreservation(fmdlFile)
	fmdlFile = FmdlAntiBlur.decodeFmdlAntiBlur(fmdlFile)
	
	return fmdlFile

def saveModel(modelFile, filename):
	modelFile = ModelSplitVertexEncoding.encodeModelVertexLoopPreservation(modelFile)
	modelFile = ModelMeshSplitting.encodeModelSplitMeshes(modelFile)
	
	ModelFile.writeModelFile(modelFile, filename)
