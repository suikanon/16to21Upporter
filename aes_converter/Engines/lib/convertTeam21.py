import os
import shutil
import struct
import sys
from PIL import Image

from . import save16, save19
from .convertFaceFolder21 import convertBootsFolder, convertFaceFolder, convertGlovesFolder
from .material import convertTextureFile
from .util import iglob, ijoin


def readString(buffer, offset):
    data = bytearray()
    while offset < len(buffer) and buffer[offset] != 0:
        data.append(buffer[offset])
        offset += 1
    return str(data, 'utf-8')


def writeString(buffer, offset, string):
    data = string.encode('utf-8') + bytes([0])
    for i in range(len(data)):
        buffer[offset + i] = data[i]


#
# Creates pes16 savedata for a player based on pes19 savedata.
#
def convertPlayerSaveData(sourcePlayerData, oldDestinationPlayerData, hasFaceModel, destinationBootsId,
                          destinationGlovesId):
    (oldPlayerData, oldPlayerAestheticsData) = oldDestinationPlayerData
    playerData = oldPlayerData[:]
    aestheticsData = oldPlayerAestheticsData[:]

    sourceAestheticsData = sourcePlayerData[116:]

    def readBits(byteOffset, bitOffset, bitCount):
        (word32,) = struct.unpack('< I', sourceAestheticsData[byteOffset: byteOffset + 4])
        return (word32 >> bitOffset) & ((1 << bitCount) - 1)

    def writeBits(byteOffset, bitOffset, bitCount, value):
        (word32,) = struct.unpack('< I', aestheticsData[byteOffset: byteOffset + 4])
        # Mask the bits to be overwritten
        word32 = word32 & ~(((1 << bitCount) - 1) << bitOffset)
        # Add the new bits
        word32 = word32 | (value << bitOffset)
        aestheticsData[byteOffset: byteOffset + 4] = struct.pack('< I', word32)

    def cap(maximum, default, value):
        if value > maximum:
            return default
        return value

    writeString(playerData, 50, readString(sourcePlayerData, 52)[0:45])  # player name
    writeString(playerData, 96, readString(sourcePlayerData, 98)[0:15])  # shirt name

    playerData[23] |= 128
    # playerData[27] |= 128

    aestheticsData[12: 19] = sourceAestheticsData[12: 19]  # body physique
    aestheticsData[22: 72] = sourceAestheticsData[22: 72]  # ingame face

    bootsId = readBits(4, 4, 14)
    glovesId = readBits(4, 18, 14)

    if destinationBootsId is not None:
        pass
    elif bootsId < 39:
        destinationBootsId = 0
    else:
        destinationBootsId = 55
    writeBits(4, 4, 14, destinationBootsId)

    if destinationGlovesId is not None:
        pass
    elif glovesId == 0:
        destinationGlovesId = 0
    elif glovesId < 11:
        destinationGlovesId = glovesId
    else:
        destinationGlovesId = 11
    writeBits(4, 18, 14, destinationGlovesId)

    if hasFaceModel:
        writeBits(4, 0, 4, 0x0c)  # edited bits
    else:
        writeBits(4, 0, 4, 0x0f)  # edited bits

    writeBits(8, 0, 32, 0)  # base copy id
    writeBits(19, 0, 6, 0)  # wrist tape color
    writeBits(19, 6, 2, 0)  # wrist tape enabled
    writeBits(20, 0, 6, readBits(20, 0, 6))  # glasses
    writeBits(20, 6, 2, readBits(20, 6, 2))  # sleeves
    writeBits(21, 0, 2, readBits(21, 0, 2))  # inners
    writeBits(21, 2, 2, readBits(21, 2, 2))  # socks
    writeBits(21, 4, 2, readBits(21, 4, 2))  # undershorts
    writeBits(21, 6, 1, readBits(21, 6, 1))  # shirttail
    writeBits(21, 7, 1, 0)  # ankle taping
    writeBits(22, 0, 4, 0)  # winter gloves

    skinColor = readBits(45, 0, 3)
    if skinColor == 7:
        # reset invisible skin
        skinColor = 1
    writeBits(45, 0, 3, skinColor)

    writeBits(45, 3, 5, cap(3, 0, readBits(45, 3, 5)))  # cheek type
    writeBits(46, 0, 3, cap(5, 0, readBits(46, 0, 3)))  # forehead type
    writeBits(46, 3, 5, cap(12, 0, readBits(46, 3, 5)))  # facial hair type
    writeBits(47, 0, 3, cap(4, 0, readBits(47, 0, 3)))  # laughter lines type
    writeBits(47, 3, 3, cap(6, 0, readBits(47, 3, 3)))  # upper eyelid type
    writeBits(48, 0, 3, cap(2, 0, readBits(48, 0, 3)))  # lower eyelid type
    writeBits(50, 0, 3, cap(5, 0, readBits(50, 0, 3)))  # eyebrow type
    writeBits(50, 5, 2, cap(2, 0, readBits(50, 5, 2)))  # neck line type
    writeBits(52, 0, 3, cap(6, 0, readBits(52, 0, 3)))  # nose type
    writeBits(53, 0, 3, cap(3, 0, readBits(53, 0, 3)))  # upper lip type
    writeBits(53, 3, 3, cap(2, 0, readBits(53, 3, 3)))  # lower lip type

    return (playerData, aestheticsData)


def mkdir(containingDirectory, name):
    existingDirectory = ijoin(containingDirectory, name)
    if existingDirectory is not None:
        return existingDirectory
    newDirectory = os.path.join(containingDirectory, name)
    os.mkdir(newDirectory)
    return newDirectory


#
# Converts a player in a PES16 export directory into a PES21 directory, and creates the save data for that player.
#
def convertPlayer(sourceDirectory, destinationDirectory, relativePlayerId, bootsGlovesBaseId, sourcePlayerData,
                  oldDestinationPlayerData):
    """
    Convert a player from PES16 format to PES21 format.

    PES16 has unified face folders containing all models (face/boots/gloves) together.
    PES21 has separate Faces/, Boots/, and Gloves/ folders at the team level.

    Args:
        sourceDirectory: PES16 export directory
        destinationDirectory: PES21 export directory
        relativePlayerId: Player number within team (1-23)
        bootsGlovesBaseId: Base ID for calculating boots/gloves IDs
        sourcePlayerData: Source player save data (PES16 format)
        oldDestinationPlayerData: Destination player save data template (PES21 format)

    Returns:
        Updated player save data for PES21
    """

    #
    # Find source unified face folder (PES16 format)
    # Get all face folders and select the one for this player based on relativePlayerId
    #
    sourceFaceDirectory = None
    sourceFacesDirectory = ijoin(sourceDirectory, "Faces")  # PES16 uses "Faces" folder
    if sourceFacesDirectory is not None:
        # Get all player folders and sort them
        playerFolders = []
        for item in os.listdir(sourceFacesDirectory):
            itemPath = os.path.join(sourceFacesDirectory, item)
            if os.path.isdir(itemPath):
                playerFolders.append(itemPath)

        # Sort folders to ensure consistent ordering
        playerFolders.sort()

        # Select the folder based on relativePlayerId (1-indexed, so subtract 1)
        folderIndex = relativePlayerId - 1
        if 0 <= folderIndex < len(playerFolders):
            sourceFaceDirectory = playerFolders[folderIndex]
        else:
            print("  WARNING: No face folder found for player index %i (only %i folders available)" % (relativePlayerId, len(playerFolders)))

    # Get boots.skl path from the example/template folder
    # TODO move that file to lib
    bootsSklPath = os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "..", "example_pes21", "numbers", "Boots", "k4226 - Cheeky Colon 3", "boots.skl")
    if not os.path.exists(bootsSklPath):
        print("WARNING: boots.skl template not found at expected location")
        bootsSklPath = None

    commonDirectory = mkdir(destinationDirectory, "Common")
    bootsId = None
    glovesId = None
    hasFaceModel = False

    if sourceFaceDirectory is not None:
        #
        # Convert the unified PES16 face folder into separate PES21 Faces/Boots/Gloves folders
        #
        # Convert using convertFaceFolder which handles splitting into separate folders
        convertFaceFolder([sourceFaceDirectory], destinationDirectory, commonDirectory, bootsSklPath)

        # Check if face models were actually created (to determine hasFaceModel)
        facesFolder = ijoin(destinationDirectory, "Faces")
        if facesFolder is not None:
            fmdlFiles = iglob(facesFolder, "*.fmdl")
            if len(fmdlFiles) > 0:
                hasFaceModel = True

        # Assign boots and gloves IDs if those folders were created
        bootsFolder = ijoin(destinationDirectory, "Boots")
        if bootsFolder is not None:
            bootsId = bootsGlovesBaseId + relativePlayerId

        glovesFolder = ijoin(destinationDirectory, "Gloves")
        if glovesFolder is not None:
            glovesId = bootsGlovesBaseId + relativePlayerId
    else:
        # No face folder found for this player - they use an in-game face
        print("  No custom face folder found for player %02i, using in-game face" % relativePlayerId)
        hasFaceModel = False

    #
    # Convert save data
    #
    # newDestinationPlayerData = convertPlayerSaveData(sourcePlayerData, oldDestinationPlayerData, hasFaceModel, bootsId, glovesId)

    # return newDestinationPlayerData


def getTeamName(sourceDirectory):
    directoryName = os.path.basename(sourceDirectory.rstrip('/\\'))
    parts = directoryName.replace("_", " ").strip().split(" ")
    return parts[0]


def getTeamId(teamListFile, teamName):
    """
    Look up a team's ID from a teams list file.

    The teams list file format is:
      <team_id> <team_name>

    For example:
      701 numbers
      702 /sp/

    Args:
        teamListFile: Path to the teams list file (teams_list_16.txt, teams_list_19.txt, or teams_list_21.txt)
        teamName: Name of the team to look up (case-insensitive)

    Returns:
        The team ID as an integer, or None if not found
    """
    for line in open(teamListFile, 'r').read().splitlines():
        # Find the space separator between ID and name
        pos = line.find(" ")
        if pos == -1:
            continue

        # Parse the team ID (left of space)
        idString = line[0:pos].strip()
        try:
            id = int(idString)
        except:
            continue

        # Parse the team name (right of space), stripping "/" characters
        nameString = line[pos + 1:].strip().strip("/")

        # Case-insensitive comparison
        if nameString.lower() == teamName.lower():
            return id

    return None


def convertKitConfigFile(kitConfigFile, destinationDirectory):
    destinationFilename = os.path.join(destinationDirectory, os.path.basename(kitConfigFile))

    kitConfigData = bytearray(open(kitConfigFile, 'rb').read())
    kitConfigData[1] = 176  # shirt type
    kitConfigData[3] = 16  # pants type
    kitConfigData[20] = 105  # collar
    kitConfigData[21] = 105  # winter collar
    # kitConfigData[27] |= 128 # tight shirts
    maskTexture = readString(kitConfigData, 72)
    if "_srm" in maskTexture:
        maskTexture = maskTexture.replace("_srm", "_mask")
        writeString(kitConfigData, 72, maskTexture)
    open(destinationFilename, 'wb').write(kitConfigData)


def convertKitTextureFile(kitTextureFile, destinationDirectory):
    basename = os.path.basename(kitTextureFile)
    if "_srm" in basename:
        #
        # Kits don't have specular maps in pes16; they have mask maps.
        # Create a sensible default one.
        #
        pos = basename.rfind('.')
        if pos == -1:
            name = basename
        else:
            name = basename[:pos]
        name = name.replace("_srm", "_mask")
        maskImage = Image.new('RGBA', (4, 4), (150, 130, 0, 255))
        maskImageFilename = os.path.join(destinationDirectory, "%s.png" % name)
        maskImage.save(maskImageFilename)
        convertTextureFile(maskImageFilename, destinationDirectory)
        os.remove(maskImageFilename)
    else:
        convertTextureFile(kitTextureFile, destinationDirectory)


def convertTeamFiles(sourceDirectory, destinationDirectory):
    #
    # note.txt
    #
    noteTxtFilenames = iglob(sourceDirectory, "*note*.txt")
    if len(noteTxtFilenames) == 0:
        print("WARNING: No note.txt found in team export folder '%s'" % sourceDirectory)
    for filename in noteTxtFilenames:
        shutil.copy(filename, os.path.join(destinationDirectory, os.path.basename(filename)))

    #
    # Logo
    #
    logoDirectory = ijoin(sourceDirectory, "Logo")
    if logoDirectory is None:
        print("WARNING: No logo folder found in team export folder '%s'" % sourceDirectory)
    else:
        shutil.copytree(logoDirectory, os.path.join(destinationDirectory, "Logo"))

    #
    # Other
    #
    otherDirectory = ijoin(sourceDirectory, "Other")
    if otherDirectory is not None:
        shutil.copytree(otherDirectory, os.path.join(destinationDirectory, "Other"))

    #
    # Kit Configs
    #
    kitConfigDirectory = ijoin(sourceDirectory, "Kit Configs")
    if kitConfigDirectory is None:
        print("WARNING: No kit config folder found in team export folder '%s'" % sourceDirectory)
    else:
        destinationKitConfigDirectory = os.path.join(destinationDirectory, "Kit Configs")
        os.mkdir(destinationKitConfigDirectory)

        for kitConfigFile in os.listdir(kitConfigDirectory):
            kitConfigPath = os.path.join(kitConfigDirectory, kitConfigFile)
            if os.path.isdir(kitConfigPath):
                #
                # kit config directory can contain its contents in a subdirectory. So recurse, once.
                #
                for kitConfigFile2 in os.listdir(kitConfigPath):
                    kitConfigPath2 = os.path.join(kitConfigPath, kitConfigFile2)
                    convertKitConfigFile(kitConfigPath2, destinationKitConfigDirectory)
            else:
                convertKitConfigFile(kitConfigPath, destinationKitConfigDirectory)

    #
    # Kit Textures
    #
    kitTextureDirectory = ijoin(sourceDirectory, "Kit Textures")
    if kitTextureDirectory is None:
        print("WARNING: No kit texture folder found in team export folder '%s'" % sourceDirectory)
    else:
        destinationKitTextureDirectory = os.path.join(destinationDirectory, "Kit Textures")
        os.mkdir(destinationKitTextureDirectory)

        for kitTextureFile in os.listdir(kitTextureDirectory):
            kitTexturePath = os.path.join(kitTextureDirectory, kitTextureFile)
            if os.path.isdir(kitTexturePath):
                #
                # kit texture directory can contain its contents in a subdirectory. So recurse, once.
                #
                for kitTextureFile2 in os.listdir(kitTexturePath):
                    kitTexturePath2 = os.path.join(kitTexturePath, kitTextureFile2)
                    convertKitTextureFile(kitTexturePath2, destinationKitTextureDirectory)
            else:
                convertKitTextureFile(kitTexturePath, destinationKitTextureDirectory)


def convertTeam(sourceDirectory, sourceSaveFile, destinationDirectory):
    teamName = getTeamName(sourceDirectory)
    print(teamName)

    sourceTeamId = getTeamId(os.path.join(os.path.dirname(os.path.realpath(__file__)), "teams_list_16.txt"), teamName)
    destinationTeamId = getTeamId(os.path.join(os.path.dirname(os.path.realpath(__file__)), "teams_list_21.txt"),
                                  teamName)
    # TODO: support a list for this
    if not destinationTeamId or not sourceTeamId: print("ERROR: Team missing from teams list files")

    bootsGlovesBaseId = 101 + (destinationTeamId - 701) * 25

    print("Converting team %i - /%s/" % (sourceTeamId, teamName))

    print("  Loading save data")
    sourceSave = save16.SaveFile()
    sourceSave.load(sourceSaveFile)

    destinationSave = save19.SaveFile()
    destinationSave.load(os.path.join(os.path.dirname(os.path.realpath(__file__)), "EDIT00000000_19"))

    sourcePlayers = save16.loadPlayers(sourceSave.payload)
    oldDestinationPlayers = save19.loadPlayers(destinationSave.payload)
    newDestinationPlayers = {}

    for i in range(23):
        print("  Converting player %02i" % (i + 1))
        sourcePlayerId = sourceTeamId * 100 + i + 1
        destinationPlayerId = destinationTeamId * 100 + i + 1

        if sourcePlayerId not in sourcePlayers:
            print("ERROR: Player %s not found in pes16 save" % sourcePlayerId)
        if destinationPlayerId not in oldDestinationPlayers:
            print("ERROR: Player %s not found in pes19 save" % destinationPlayerId)

        sourcePlayer = sourcePlayers[sourcePlayerId]
        oldDestinationPlayer = oldDestinationPlayers[destinationPlayerId]

        print(oldDestinationPlayer)
        oldDestinationPlayerData = oldDestinationPlayer
        if oldDestinationPlayerData is None:
            print("ERROR: Incomplete player %s found in pes19 save" % destinationPlayerId)

        newDestinationPlayers[destinationPlayerId] = convertPlayer(
            sourceDirectory,
            destinationDirectory,
            i + 1,
            bootsGlovesBaseId,
            sourcePlayer,
            oldDestinationPlayer,
        )

    print("  Converting kits")
    commonDirectory = ijoin(destinationDirectory, "Common")
    if commonDirectory is not None and len(os.listdir(commonDirectory)) == 0:
        os.rmdir(commonDirectory)

    convertTeamFiles(sourceDirectory, destinationDirectory)

    print("  Creating save")
    save16.savePlayers(destinationSave.payload, newDestinationPlayers)
    destinationSave.save(os.path.join(destinationDirectory, "EDIT00000000"))


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Usage: convertTeam <pes19 export folder> <pes19 savefile> <destination folder>")
        sys.exit(1)

    convertTeam(sys.argv[1], sys.argv[2], sys.argv[3])
