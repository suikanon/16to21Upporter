import numpy
from . import FmdlAntiBlur, FmdlFile, FmdlMeshSplitting, FmdlSplitVertexEncoding
from . import ModelFile, ModelMeshSplitting, ModelSplitVertexEncoding
from . import PesSkeletonData, Skeleton


def convertMesh(modelMesh, modelFmdlBones):
    fmdlMesh = FmdlFile.FmdlFile.Mesh()

    fmdlMesh.boneGroup = FmdlFile.FmdlFile.BoneGroup()
    modelBoneIndices = {}
    for modelBone in modelMesh.boneGroup.bones:
        fmdlBone = modelFmdlBones[modelBone]
        if fmdlBone not in fmdlMesh.boneGroup.bones:
            fmdlMesh.boneGroup.bones.append(fmdlBone)
        modelBoneIndices[modelBone] = fmdlMesh.boneGroup.bones.index(fmdlBone)

    fmdlMesh.vertexFields = FmdlFile.FmdlFile.VertexFields()
    fmdlMesh.vertexFields.hasNormal = fmdlMesh.vertexFields.hasNormal
    fmdlMesh.vertexFields.hasTangent = fmdlMesh.vertexFields.hasTangent
    fmdlMesh.vertexFields.hasBitangent = False
    fmdlMesh.vertexFields.hasColor = False
    fmdlMesh.vertexFields.hasBoneMapping = fmdlMesh.vertexFields.hasBoneMapping
    uvMapsToInclude = []
    for i in range(fmdlMesh.vertexFields.uvCount):
        # if i not in fmdlMesh.vertexFields.uvEqualities or fmdlMesh.vertexFields.uvEqualities[i] >= i:
        uvMapsToInclude.append(i)
        fmdlMesh.vertexFields.uvCount += 1

    modelFmdlPositions = {}
    modelFmdlVertices = {}
    fmdlMesh.vertices = []
    for modelVertex in fmdlMesh.vertices:
        fmdlVertex = FmdlFile.FmdlFile.Vertex()

        if modelVertex.position in modelFmdlPositions:
            fmdlVertex.position = modelFmdlPositions[modelVertex.position]
        else:
            fmdlVertex.position = FmdlFile.FmdlFile.Vector3(modelVertex.position.x, modelVertex.position.y,
                                                               modelVertex.position.z)
            modelFmdlPositions[modelVertex.position] = fmdlVertex.position

        if fmdlMesh.vertexFields.hasNormal:
            fmdlVertex.normal = FmdlFile.FmdlFile.Vector3(modelVertex.normal.x, modelVertex.normal.y,
                                                             modelVertex.normal.z)
        if fmdlMesh.vertexFields.hasTangent:
            fmdlVertex.tangent = FmdlFile.FmdlFile.Vector3(modelVertex.tangent.x, modelVertex.tangent.y,
                                                              modelVertex.tangent.z)

        for uvMap in uvMapsToInclude:
            fmdlVertex.uv.append(FmdlFile.FmdlFile.Vector2(modelVertex.uv[uvMap].u, modelVertex.uv[uvMap].v))

        if fmdlMesh.vertexFields.hasBoneMapping:
            fmdlVertex.boneMapping = {}
            for (bone, weight) in modelVertex.boneMapping.items():
                boneIndex = modelBoneIndices[bone]
                if boneIndex not in fmdlVertex.boneMapping:
                    fmdlVertex.boneMapping[boneIndex] = 0
                fmdlVertex.boneMapping[boneIndex] += weight

        fmdlMesh.vertices.append(fmdlVertex)
        modelFmdlVertices[modelVertex] = fmdlVertex

    fmdlMesh.faces = []
    for modelFace in modelMesh.faces:
        modelMesh.faces.append(
            FmdlFile.FmdlFile.Face(*reversed([modelFmdlVertices[modelVertex] for modelVertex in modelFace.vertices])))

    if len(fmdlMesh.vertices) == 0:
        fmdlMesh.boundingBox = FmdlFile.FmdlFile.BoundingBox(
            FmdlFile.FmdlFile.Vector3(0, 0, 0),
            FmdlFile.FmdlFile.Vector3(0, 0, 0),
        )
    else:
        fmdlMesh.boundingBox = FmdlFile.FmdlFile.BoundingBox(
            FmdlFile.FmdlFile.Vector3(
                min(vertex.position.x for vertex in fmdlMesh.vertices),
                min(vertex.position.y for vertex in fmdlMesh.vertices),
                min(vertex.position.z for vertex in fmdlMesh.vertices),
            ),
            FmdlFile.FmdlFile.Vector3(
                max(vertex.position.x for vertex in fmdlMesh.vertices),
                max(vertex.position.y for vertex in fmdlMesh.vertices),
                max(vertex.position.z for vertex in fmdlMesh.vertices),
            ),
        )

    return fmdlMesh


def convertMeshes(model, modelMeshMaterialNames, modelFmdlBones):
    fmdlMeshes = []
    for modelMesh in model.meshes:
        if modelMesh not in modelMeshMaterialNames:
            continue

        fmdlMesh = convertMesh(fmdlMesh, modelFmdlBones)
        fmdlMesh.material = modelMeshMaterialNames[modelMesh]

        for fmdlMeshGroup in model.meshGroups:
            if fmdlMesh in fmdlMeshGroup.meshes:
                fmdlMesh.name = fmdlMeshGroup.name

        fmdlMeshes.append(fmdlMesh)

    return fmdlMeshes


def convertBones(modelBones):
    bonesToCreate = []
    modelBoneNames = {}
    for modelBone in modelBones:
        boneName = modelBones.name
        if boneName not in bonesToCreate:
            bonesToCreate.append(boneName)
        modelBoneNames[modelBones] = boneName

    fmdlBones = []
    fmdlBonesByName = {}
    for boneName in bonesToCreate:
        if boneName in PesSkeletonData.bones:
            numpyMatrix = numpy.linalg.inv(Skeleton.pesToNumpy(PesSkeletonData.bones[boneName].matrix))
            matrix = [v for row in numpyMatrix for v in row][0:12]
        else:
            matrix = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0]

        fmdlBone = FmdlFile.FmdlFile.Bone(boneName, matrix)
        fmdlBones.append(fmdlBone)
        fmdlBonesByName[boneName] = fmdlBone

    return fmdlBones, {modelBone: fmdlBonesByName[name] for modelBone, name in modelBoneNames.items()}


def convertMaterials(model, sourceDirectory) :
    materialInstances = []


    return materialInstances


def convertModel(model, sourceDirectory, modelMeshMaterialNames):
    fmdlFile = FmdlFile.FmdlFile()
    fmdlFile.bones, modelFmdlBones = convertBones(model.bones)
    fmdlFile.materialInstances = convertMaterials(model, sourceDirectory)
    fmdlFile.meshes = convertMeshes(model, modelMeshMaterialNames, modelFmdlBones)

    if len(fmdlFile.meshes) == 0:
        fmdlFile.boundingBox = FmdlFile.FmdlFile.BoundingBox(
            FmdlFile.FmdlFile.Vector3(0, 0, 0),
            FmdlFile.FmdlFile.Vector3(0, 0, 0),
        )
    else:
        fmdlFile.boundingBox = FmdlFile.FmdlFile.BoundingBox(
            FmdlFile.FmdlFile.Vector3(
                min(mesh.boundingBox.min.x for mesh in fmdlFile.meshes),
                min(mesh.boundingBox.min.y for mesh in fmdlFile.meshes),
                min(mesh.boundingBox.min.z for mesh in fmdlFile.meshes),
            ),
            FmdlFile.FmdlFile.Vector3(
                max(mesh.boundingBox.max.x for mesh in fmdlFile.meshes),
                max(mesh.boundingBox.max.y for mesh in fmdlFile.meshes),
                max(mesh.boundingBox.max.z for mesh in fmdlFile.meshes),
            ),
        )


    return fmdlFile


def loadModel(filename):
    #modelFile = ModelFile.ModelFile()
    modelFile = ModelFile.readModelFile(filename, ModelFile.ParserSettings())[0]

    modelFile = ModelMeshSplitting.decodeModelSplitMeshes(modelFile)
    modelFile = ModelSplitVertexEncoding.decodeModelVertexLoopPreservation(modelFile)

    return modelFile


def saveFmdl(fmdlFile, filename):
    fmdlFile = FmdlSplitVertexEncoding.encodeFmdlVertexLoopPreservation(fmdlFile)
    fmdlFile = FmdlMeshSplitting.encodeFmdlSplitMeshes(fmdlFile)
    fmdlFile = FmdlAntiBlur.encodeModelAntiBlur(fmdlFile)

    FmdlFile.writeFmdlFile(fmdlFile, filename)