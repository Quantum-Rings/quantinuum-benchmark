import os
from os import listdir

import qiskit
from qiskit import transpile

import json
from pytket.circuit import Circuit

from pytket.extensions.qiskit import tk_to_qiskit
from pytket.passes import FullPeepholeOptimise, SequencePass, RemoveRedundancies
from pytket.passes import DecomposeBoxes

def transpile_pytket_json( circuit_name, json_path, output_path ):
    print (f"Transpiling circuit: {circuit_name}")
    print (f"Input path: {json_path}")
    print (f"Output path: {output_path}")
    
    json_file = os.path.join(json_path, circuit_name + ".json")
    output_file = os.path.join(output_path, circuit_name + ".qasm")

    print(f"TranspilingPyTketJson. Input file: {json_file} Output file: {output_file}")

    # Load the JSON data
    with open(json_file, 'r') as f:
        circuit_json = json.load(f)

    # Create a Circuit object from the JSON dictionary
    tket_circ = Circuit.from_dict(circuit_json)

    # Remove the PauliExpBoxes and flatten the circuit
    DecomposeBoxes().apply(tket_circ)

    # Optimize the circuit
    #opt_pass = SequencePass([FullPeepholeOptimise(), RemoveRedundancies()])

    # Apply optimizations to the circuit
    #opt_pass.apply(tket_circ)

    # Convert to Qiskit circuit
    opt_qiskit_circ = tk_to_qiskit(tket_circ, replace_implicit_swaps = True, perm_warning=True)

    # get rid of complex arithmetic expressions in the gate instructions and convert V or Vdg (if any) to simpler gates
    qc = transpile(opt_qiskit_circ, basis_gates=['u3', 'cx', 'h', 'x'], optimization_level=3)

    # Export to QASM
    qiskit.qasm2.dump(qc, output_file)

    print("Done")

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description="Transpile a PyTket JSON circuit.")
    parser.add_argument("circuit_name", type=str,
                        help="The name of the circuit (e.g., 'bell_state').")
    parser.add_argument("source_folder", type=str,
                        help="The path to the folder containing the source circuit files.")
    parser.add_argument("dest_folder", type=str,
                        help="The path to the folder where transpiled circuits will be saved.")

    args = parser.parse_args()

    transpile_pytket_json(args.circuit_name, args.source_folder, args.dest_folder)
