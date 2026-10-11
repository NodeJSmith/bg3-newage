// Minimal LSLib front end. Divine.exe's CLI rejects absolute paths on Linux
// ("This operation is not supported for a relative URI"), so this calls the
// library directly.
using LSLib.LS;
using LSLib.LS.Enums;

if (args.Length != 3)
{
    Console.Error.WriteLine("Usage: lsltool extract <save.lsv|file.pak> <destDir>");
    Console.Error.WriteLine("       lsltool lsf2lsx <src.lsf> <dest.lsx>");
    return 1;
}

// LSLib also refuses relative paths, so resolve them here
var (cmd, src, dest) = (args[0], Path.GetFullPath(args[1]), Path.GetFullPath(args[2]));

switch (cmd)
{
    case "extract":
        new Packager().UncompressPackage(src, dest, null);
        break;

    case "lsf2lsx":
        var resource = ResourceUtils.LoadResource(
            src, ResourceFormat.LSF, ResourceLoadParameters.FromGameVersion(Game.BaldursGate3));
        ResourceUtils.SaveResource(
            resource, dest, ResourceFormat.LSX, ResourceConversionParameters.FromGameVersion(Game.BaldursGate3));
        break;

    default:
        Console.Error.WriteLine($"Unknown command: {cmd}");
        return 1;
}

Console.WriteLine($"{cmd}: {src} -> {dest}");
return 0;
