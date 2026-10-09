"""Prepare fixed operator input folders without touching exports or credentials."""
import argparse
import json
from pathlib import Path
from .domain import ValidationError, path_is_link, require, safe_path, write_new
from .layout import require_layout

INPUT_DIRECTORIES=('Endeavor','certificates','supplemental/JCL','supplemental/JCLPlus',
                   'supplemental/PROCConverted','supplemental/Copybooks','supplemental/ControlCards')


def initialize_inputs(workspace):
    root=Path(workspace).absolute()
    require_layout(root)
    require(not path_is_link(root) and not any(path_is_link(p) for p in root.parents),
            'Use a local workspace without symlink parents')
    destinations=[safe_path(root,rel) for rel in INPUT_DIRECTORIES]
    manifest=safe_path(root,'Process.md')
    # Inspect every destination before writing any template. Existing inputs stay untouched.
    for destination in destinations:
        require(not path_is_link(destination) and (not destination.exists() or destination.is_dir()),
                'Input folder must be a regular directory: '+destination.relative_to(root).as_posix())
    require(not path_is_link(manifest) and (not manifest.exists() or manifest.is_file()),
            'Process.md must be a regular Markdown file')
    root.mkdir(parents=True,exist_ok=True)
    created=[]
    for destination in destinations:
        if not destination.exists():
            destination.mkdir(parents=True,exist_ok=True)
            created.append(destination.relative_to(root).as_posix())
    if not manifest.exists():
        template=Path(__file__).resolve().parents[1]/'examples/process-specific.md'
        try:write_new(manifest,template.read_bytes())
        except FileExistsError:
            require(manifest.is_file() and not path_is_link(manifest),'Process.md changed during preparation')
        else:created.append('Process.md')
    require_layout(root)
    return {'workspace':str(root),'process_file':str(manifest),'created':created,
            'source_folder':str(root/'Endeavor'),'certificate_folder':str(root/'certificates'),
            'supplemental_policy':'Use only for exact missing objects after approved read-only retrieval; not scanned by default.',
            'connectivity_verified':False}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace',default=str(Path.cwd()))
    args=parser.parse_args(argv)
    try:result=initialize_inputs(args.workspace)
    except (ValidationError,OSError) as exc:
        print('Input preparation stopped: '+str(exc));return 2
    print(json.dumps(result,indent=2));return 0


if __name__=='__main__':raise SystemExit(main())
