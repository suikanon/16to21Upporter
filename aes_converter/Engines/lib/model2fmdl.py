import numpy
import os
import xml.etree.ElementTree as ET
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
    fmdlMesh.vertexFields.hasNormal = modelMesh.vertexFields.hasNormal
    fmdlMesh.vertexFields.hasTangent = modelMesh.vertexFields.hasTangent
    fmdlMesh.vertexFields.hasBitangent = False
    fmdlMesh.vertexFields.hasColor = False
    fmdlMesh.vertexFields.hasBoneMapping = modelMesh.vertexFields.hasBoneMapping
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
        boneName = modelBone.name
        if boneName not in bonesToCreate:
            bonesToCreate.append(boneName)
        modelBoneNames[modelBone] = boneName

    fmdlBones = []
    fmdlBonesByName = {}
    for boneName in bonesToCreate:
        if boneName in PesSkeletonData.bones:
            numpyMatrix = numpy.linalg.inv(Skeleton.pesToNumpy(PesSkeletonData.bones[boneName].matrix))
            matrix = [v for row in numpyMatrix for v in row][0:12]
        else:
            matrix = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0]

        fmdlBone = FmdlFile.FmdlFile.Bone(boneName, matrix)
        fmdlBone.name = boneName
        fmdlBones.append(fmdlBone)
        fmdlBonesByName[boneName] = fmdlBone

    return fmdlBones, {modelBone: fmdlBonesByName[name] for modelBone, name in modelBoneNames.items()}


def convertMaterials(model, sourceDirectory):
    """
    Convert materials from ModelFile format to FmdlFile MaterialInstance format.

    Args:
        model: ModelFile object containing materials
        sourceDirectory: Path to directory containing .model file and .mtl files

    Returns:
        List of FmdlFile.MaterialInstance objects
    """
    materialInstances = []
    print("0")
    # Find all .mtl files in the source directory
    mtlFiles = []
    if os.path.isdir(sourceDirectory):
        for filename in os.listdir(sourceDirectory):
            if filename.lower().endswith('.mtl'):
                mtlFiles.append(os.path.join(sourceDirectory, filename))

    print("1")
    # Parse all .mtl files to build a material database
    mtlMaterials = {}  # name -> material XML element
    for mtlFile in mtlFiles:
        try:
            tree = ET.parse(mtlFile)
            root = tree.getroot()

            # Find all <material> elements
            for materialElement in root.findall('material'):
                print("name")
                print(materialElement)
                materialName = materialElement.get('name')
                print(materialName)
                if materialName:
                    mtlMaterials[materialName] = materialElement
        except Exception as e:
            print(f"WARNING: Failed to parse .mtl file {mtlFile}: {e}")

    print("2")
    # Process each material from the ModelFile
    for materialName in model.materials:
        materialInstance = FmdlFile.FmdlFile.MaterialInstance()
        materialInstance.name = materialName

        print(materialName)
        # Check if material exists in .mtl files
        if materialName in mtlMaterials:
            materialElement = mtlMaterials[materialName]
            shader = materialElement.get('shader', '')

            # Assign technique and shader based on shader type
            if shader == 'Basic_C':
                materialInstance.technique = 'fox3DDF_Blin'
                materialInstance.shader = 'fox3ddf_blin'
            else:
                materialInstance.technique = 'fox3DFW_ConstantSRGB_NDR'
                materialInstance.shader = 'fox3dfw_constant_srgb_ndr'

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

                # Extract filename from path (remove ./ prefix if present)
                if texturePath.startswith('./'):
                    texturePath = texturePath[2:]

                texture.filename = os.path.basename(texturePath)

                # Determine directory based on model type
                # Check if this is a face model or boots model
                if 'face' in materialName.lower() or 'hair' in materialName.lower() or 'oral' in materialName.lower():
                    texture.directory = '/Assets/pes16/model/character/face/real/75314/sourceimages/'
                else:
                    texture.directory = '/Assets/pes16/model/character/boots/k0051/'

                # Add texture to materialInstance with 'Base_Tex_SRGB' key
                materialInstance.textures = [('Base_Tex_SRGB', texture)]
            else:
                materialInstance.textures = []
        else:
            # Material not found in .mtl file, use default values
            print(f"WARNING: Material '{materialName}' not found in .mtl files, using defaults")
            materialInstance.technique = 'fox3DFW_ConstantSRGB_NDR'
            materialInstance.shader = 'fox3dfw_constant_srgb_ndr'
            materialInstance.textures = []

        # Parameters field is left empty as per requirements
        materialInstance.parameters = []

        materialInstances.append(materialInstance)
    return materialInstances


def convertModel(model, sourceDirectory):
    print("preamp")
    fmdlFile = FmdlFile.FmdlFile()
    print(model.bones)
    #fmdlFile.bones, modelFmdlBones = convertBones(model.bones)
    print("convertModel")
    print(sourceDirectory)
    fmdlFile.init()
    fmdlFile.materialInstances = convertMaterials(model, sourceDirectory)
    fmdlFile.meshes = convertMeshes(model, ["name"], modelFmdlBones)

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