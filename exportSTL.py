import opensim as osim
import numpy as np
import stl
from stl import mesh
import argparse
import os

class Geometry:
    def __init__(self, name, body, t):
        self.name = name
        self.body = body
        self.t = t

def process_files(infile, outdir):
    if not os.path.exists(outdir):
        os.makedirs(outdir)

    model = osim.Model(infile)
    s = model.initSystem()

    bodies = []

    for body in model.getBodySet():
        print(body.getName())

        # Check if geometry exists (could be just a joint)
        check_geom_string = body.getPropertyByName("attached_geometry").toString()
        mesh_file_name = "none"
        if check_geom_string == "(Mesh)":
            geom = body.get_attached_geometry(0)
            mesh_file_name = geom.getPropertyByName("mesh_file").toString()

        name = body.getName()
        p = body.getPositionInGround(s)
        r = body.getTransformInGround(s).R()

        # Construct Transformation matrix (4x4)
        t = np.array([[r.get(0,0),r.get(0,1),r.get(0,2),p.get(0)],
                     [r.get(1,0),r.get(1,1),r.get(1,2),p.get(1)],
                     [r.get(2,0),r.get(2,1),r.get(2,2),p.get(2)],
                     [0,0,0,1]])

        mesh_geom = Geometry(name, mesh_file_name, t)
        bodies.append(mesh_geom)

    # Get ground object
    ground = model.get_ground()
    ground.getPropertyByName("attached_geometry").toString()
    ground_mesh_name = "none"
    if check_geom_string == "(Mesh)":
        geom = ground.get_attached_geometry(0)
        ground_mesh_name = geom.getPropertyByName("mesh_file").toString()

    meshes = []

    print("Converting "+str(len(bodies))+" bodies...")
    for body in bodies:
        print("Processing:"+body.name)
        if body.body != "none":
            # Change from vtp to stl too
            body_mesh = mesh.Mesh.from_file("Geometry/"+body.body)
        else:
            # Use cube for joints
            # body_mesh = mesh.Mesh(cube_mesh.copy())
            body_mesh = mesh.Mesh.from_file("reference_cube.stl")

        body_mesh.transform(body.t)
        body_mesh.save(outdir+"/"+body.name+".stl", mode=stl.Mode.ASCII)
        meshes.append(body_mesh)

    # Save ground mesh (needs no transform)
    if body.body != "none":
        # Change from vtp to stl too
        ground_mesh = mesh.Mesh.from_file("Geometry/"+ground_mesh_name)
    else:
        # Use cube for joints
        ground_mesh = mesh.Mesh.from_file("reference_cube.stl")
    ground_mesh.save(outdir+"/ground_mesh.stl", mode=stl.Mode.ASCII)
    meshes.append(ground_mesh)
    print("Exporting Combined Mesh...")
    combined = mesh.Mesh(np.concatenate([combine.data for combine in meshes]))
    combined.save(outdir+"/combined_mesh.stl", mode=stl.Mode.ASCII)

def run(args):
    process_files(args.infile, args.outdir)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="OpenSim STL Exporter")
    parser.add_argument('infile', help="Path to input file.")
    parser.add_argument('--outdir', '-o', default='output', help="Path to output directory.")
    parser.set_defaults(func=run)
    args = parser.parse_args()
    ret = args.func(args)
