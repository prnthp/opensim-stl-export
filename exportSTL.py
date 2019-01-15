import opensim as osim
import numpy as np
import stl
from stl import mesh
import argparse
import os
import math

class Geometry:
    def __init__(self, name, body, t):
        self.name = name
        self.body = body
        self.t = t

def find_geom_by_body(name, geometries):
    for geom in geometries:
        if geom.name == name:
            return geom
    return null

def rotate_from_to(a,b):
    # a,b are vectors of size 3
    # https://math.stackexchange.com/questions/180418/calculate-rotation-matrix-to-align-vector-a-to-vector-b-in-3d
    v = np.cross(a,b)
    c = np.dot(a,b)
    vskew = np.array([[0,-v[2],v[1]],[v[2],0,-v[0]],[-v[1],v[0],0]])
    if c-1 == 0:
        return np.eye(3)
    coeff = 1/(1+c)
    R = np.eye(3) + vskew + np.dot(vskew,vskew)*coeff
    return R

def rotation_matrix(angle, direction, point=None):
    """Return matrix to rotate about axis defined by point and direction.
    https://www.lfd.uci.edu/~gohlke/code/transformations.py.html
    """
    sina = math.sin(angle)
    cosa = math.cos(angle)
    direction = unit_vector(direction[:3])
    # rotation matrix around unit vector
    R = np.diag([cosa, cosa, cosa])
    R += np.outer(direction, direction) * (1.0 - cosa)
    direction *= sina
    R += np.array([[ 0.0,         -direction[2],  direction[1]],
                      [ direction[2], 0.0,          -direction[0]],
                      [-direction[1], direction[0],  0.0]])
    M = np.identity(4)
    M[:3, :3] = R
    if point is not None:
        # rotation not around origin
        point = np.array(point[:3], dtype=np.float64, copy=False)
        M[:3, 3] = point - np.dot(R, point)
    return M

def unit_vector(data, axis=None, out=None):
    """Return ndarray normalized by length, i.e. Euclidean norm, along axis.
    https://www.lfd.uci.edu/~gohlke/code/transformations.py.html
    """
    if out is None:
        data = np.array(data, dtype=np.float64, copy=True)
        if data.ndim == 1:
            data /= math.sqrt(np.dot(data, data))
            return data
    else:
        if out is not data:
            out[:] = np.array(data, copy=False)
        data = out
    length = np.atleast_1d(np.sum(data*data, axis))
    np.sqrt(length, length)
    if axis is not None:
        length = np.expand_dims(length, axis)
    data /= length
    if out is None:
        return data

def process_files(infile, outdir, jointsonly):
    if not os.path.exists(outdir):
        os.makedirs(outdir)

    model = osim.Model(infile)
    s = model.initSystem()

    bodies = []

    for body in model.getBodySet():
        print(body.getName())

        # Check if geometry exists (could be just a joint)
        check_geom_string = body.getPropertyByName('attached_geometry').toString()
        mesh_file_name = 'none'
        if check_geom_string == '(Mesh)':
            geom = body.get_attached_geometry(0)
            mesh_file_name = geom.getPropertyByName('mesh_file').toString()

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

    coords = dict()
    cs = model.getCoordinateSet()
    for i in range(model.getNumCoordinates()):
        coords[cs.get(i).toString()] = cs.get(i).getValue(s)

    joints = []

    for joint in model.getJointSet():
        if joint.getNumProperties() < 6:
            continue
        if joint.numCoordinates() == 0:
            continue

        print(joint.getName())

        f = joint.getParentFrame()
        sock = f.getSocket('parent')
        body_name = sock.getConnecteePath()
        body_name = body_name.split('/')[-1]
        geom = find_geom_by_body(body_name, bodies)

        p = f.getPositionInGround(s)

        st = joint.getPropertyByName('SpatialTransform')

        r_str = []
        r_name = []
        r = []
        R = []

        for i in range(3):
            t = np.copy(geom.t)
            R_body = t[0:3,0:3]

            coord_name = st.getValueAsObject().getPropertyByIndex(i).getValueAsObject().getPropertyByIndex(0).toString().strip('()')
            if coord_name == '':
                continue

            r_name.append(coord_name)
            r_str.append(st.getValueAsObject().getPropertyByIndex(i).getValueAsObject().getPropertyByIndex(1).toString().strip('()').split(' '))
            r.append([float(j) for j in r_str[-1]])
            # arrow (0,1,0)
            y_axis = np.array([0,1,0])

            # rorate around y-axis to coordinate
            R_coord = rotation_matrix(coords[coord_name], y_axis)

            # rotation to align y-axis to rotational axis
            R_rot = rotate_from_to(y_axis, r[-1])

            # Original solution (wrong, but gets the job half-done)
            # R.append(np.dot(R_body,R_rot)) # align y-axis

            R.append(np.dot(R_body,R_rot)) # align y-axi
            R[-1] = np.dot(R[-1],R_coord[0:3,0:3]) # rotate around rot-axis

            t[0:3,0:3] = R[-1]
            t[0,3] = p.get(0) # but point to actual pivot
            t[1,3] = p.get(1)
            t[2,3] = p.get(2)

            mesh_geom = Geometry(('joint-'+coord_name), 'joint', t)
            joints.append(mesh_geom)


    # Get ground object
    ground = model.get_ground()
    ground.getPropertyByName('attached_geometry').toString()
    ground_mesh_name = 'none'
    if check_geom_string == '(Mesh)':
        geom = ground.get_attached_geometry(0)
        ground_mesh_name = geom.getPropertyByName('mesh_file').toString()

    bodies = bodies + joints # concat lists
    meshes = []

    print('Converting '+str(len(bodies))+' bodies...')
    for body in bodies:
        print('Processing:'+body.name)
        if body.body == 'none':
            body_mesh = mesh.Mesh.from_file('reference_cube.stl')
        elif body.body == 'joint':
            body_mesh = mesh.Mesh.from_file('reference_arrow.stl')
        else:
            if jointsonly:
                continue
            body_mesh = mesh.Mesh.from_file('Geometry/'+body.body)

        body_mesh.transform(body.t)
        body_mesh.save(outdir+'/'+body.name+'.stl', mode=stl.Mode.ASCII)
        meshes.append(body_mesh)

    # Save ground mesh (needs no transform)
    if ground_mesh_name != 'none' and not jointsonly:
        # Change from vtp to stl too
        ground_mesh = mesh.Mesh.from_file('Geometry/'+ground_mesh_name)
    else:
        # Use cube for joints
        ground_mesh = mesh.Mesh.from_file('reference_cube.stl')
    ground_mesh.save(outdir+'/ground_mesh.stl', mode=stl.Mode.ASCII)
    meshes.append(ground_mesh)
    print('Exporting Combined Mesh...')
    combined = mesh.Mesh(np.concatenate([combine.data for combine in meshes]))
    combined.save(outdir+'/combined_mesh.stl', mode=stl.Mode.ASCII)

def run(args):
    process_files(args.infile, args.outdir, args.jointsonly)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='OpenSim STL Exporter')
    parser.add_argument('infile', help='Path to input file.')
    parser.add_argument('--outdir', '-o', default='output', help='Path to output directory.')
    parser.add_argument('--jointsonly', '-j', help='Only joints should be exported as reference_cube.stl and reference_arrow.stl',action='store_true')
    parser.set_defaults(func=run)
    args = parser.parse_args()
    ret = args.func(args)
