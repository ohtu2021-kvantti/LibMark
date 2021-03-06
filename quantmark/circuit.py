import re
import typing
from dataclasses import dataclass
import tequila as tq
from tequila.circuit.circuit import QCircuit
from quantmark.exceptions.same_control_and_target import SameControlAndTarget
from quantmark.exceptions.invalid_syntax_error import InvalidSyntaxError
from quantmark.create_multiline_regex import create_multiline_regex

# Regex for the non parametrized single qubit gates X, Y, Z and H.
NP_ONEQ_GATES_REGEX = r"(X|Y|Z|H)\(target=\(\d+,\)(, control=\((\d+,|\d+(, \d+)+)\))?\)"

# Regex for the parametrized single qubit gates Phase, Rx, Ry and Rz.
P_ONEQ_GATES_REGEX = r"(Phase|Rx|Ry|Rz)\(target=\(\d+,\)(, control=\((\d+,|\d+(, \d+)+)\))?,"\
	r" parameter=((\d+.\d*)|\D*)\)"

# Regex for the SWAP gate.
SWAP_GATE_REGEX = r"SWAP\(target=\(\d*, \d*\)(, control=\((\d+,|\d+(, \d+)+|)\))?\)"


@dataclass
class GateDict:
	"""A dataclass used during circuit construction from string."""
	name: str
	target: typing.List[str]
	control: typing.List[str] = None
	parameter: typing.Union[str, float] = None


class CircuitInfo:
	"""
	An object returned when analyzing a circuit, that holds information about it.

	Attributes
	----------
		gate_depth : int
			The gate depth of the circuit.
		qubit_count : int
			The amount of qubits the circuit needs.
		gate_count : int
			The amount of gates the circuit uses.
		parameter_count : int
			The amount of parameters on the circuit that have to be optimized.

	Methods
	----------
		__str__ : str
			Prints all attributes (one per line).
	"""
	def __init__(self, circuit: QCircuit):
		"""
		Creates a CircuitInfo object. This can be used to get information about a circuit,

		Parameters
		----------
			circuit : QCircuit
				The circuit that you want information about.
		"""
		self._qubit_count = circuit.n_qubits
		self._gate_depth = circuit.depth
		self._gate_count = len(circuit.gates)
		self._parameter_count = len(list(circuit.make_parameter_map().keys()))

	@property
	def gate_depth(self) -> int:
		"""The gate depth of the circuit."""
		return self._gate_depth

	@property
	def qubit_count(self) -> int:
		"""The amount of qubits the circuit needs."""
		return self._qubit_count

	@property
	def gate_count(self) -> int:
		"""The amount of gates the circuit uses."""
		return self._gate_count

	@property
	def parameter_count(self) -> int:
		"""The amount of parameters on the circuit that have to be optimized."""
		return self._parameter_count

	def __str__(self) -> str:
		"""Prints all attributes (one per line)."""
		return (
			f'QUBIT COUNT:        {self.qubit_count}\n'
			f'GATE DEPTH:         {self.gate_depth}\n'
			f'GATE COUNT:         {self.gate_count}\n'
			f'PARAMETER COUNT:    {self.parameter_count}\n'
		)


def circuit_pattern(compile: bool = True) -> typing.Union[typing.Pattern[str], str]:
	"""
	Creates a regex pattern for recognizing circuits(QCircuit.__str__).

	Parameters
	----------
		compile : bool
			If true the regex is compiled, otherwise it is returned as a string.

	Returns
	----------
	Returns a compiled pattern or string depending on the compile parameter.
	"""
	options = [NP_ONEQ_GATES_REGEX, P_ONEQ_GATES_REGEX, SWAP_GATE_REGEX]
	return create_multiline_regex(options, first_line='circuit:', compile=compile)


def validate_circuit_syntax(circuit: str) -> bool:
	"""
	Checks if the syntax of a string is valid so that it can be turned into a QCircuit.

	Parameters
	----------
		circuit : str
			The string representing the circuit. (Obtained with QCircuit.__str__)

	Returns
	----------
	True when the circuit syntax is valid and false otherwise.
	"""
	return bool(circuit_pattern().match(circuit))


def get_one_gate_data_from_string(string: str, data: str) -> typing.List[int]:
	"""
	Gets certain data from a string that represents a gate.

	Parameters
	----------
		string : str
			A string representing a gate.
		data : str
			The name of the data that is wanted. The options are 'target' and 'control'.

	Returns
	----------
	A list containing the wanted data.
	"""
	target_area = string.split(f'{data}=(', 1)[1].split(")")[0]
	parts = target_area.split(',')
	if not parts[-1]:
		parts = parts[:-1]
	return [int(n) for n in parts]


def get_gate_parameter(string: str) -> typing.Union[float, str]:
	"""
	Gets a parameter from a gate.

	Parameters
	----------
		string : str
			A string representing a gate.

	Returns
	----------
	Returns the parameter as a string if it is a variable, or as a float if it has a set value.
	"""
	string_patrameter = string.split("parameter=", 1)[1].split(")")[0]
	try:
		float_parameter = float(string_patrameter)
		return float_parameter
	except ValueError:
		return string_patrameter


def gate_string_to_dict(string: str) -> GateDict:
	"""
	Saves the information from a string representing a gate to a dataclass for easy handling.

	Parameters
	----------
		string : str
			A string representing a gate.

	Returns
	----------
	A GateDict dataclass representing a gate.
	"""
	name = string.split("(", 1)[0]
	target = get_one_gate_data_from_string(string, 'target')
	control = None
	if 'control' in string:
		control = get_one_gate_data_from_string(string, 'control')
	parameter = None
	if 'parameter' in string:
		parameter = get_gate_parameter(string)
	return GateDict(name=name, target=target, control=control, parameter=parameter)


def gate_from_gate_dict(gate: GateDict) -> QCircuit:
	"""
	Transforms a GateDict to a QCircuit object representing that gate.

	Parameters
	----------
		gate : GateDict
			The GateDict object that will be transformed int a Qcircuit object.

	Returns
	----------
	A QCircuit object representing a single gate.
	"""
	if gate.control and set(gate.target) & set(gate.control):
		raise SameControlAndTarget
	if gate.name in ['X', 'Y', 'Z', 'H']:
		gate_method = getattr(tq.gates, gate.name)
		return gate_method(target=gate.target, control=gate.control)
	if gate.name in ['Rx', 'Ry', 'Rz']:
		gate_method = getattr(tq.gates, gate.name)
		return gate_method(gate.parameter, target=gate.target, control=gate.control)
	if gate.name in ['Phase']:
		return tq.gates.Phase(phi=gate.parameter, target=gate.target, control=gate.control)
	if gate.name in ['SWAP']:
		first, second = gate.target
		return tq.gates.SWAP(first=first, second=second, control=gate.control)
	return None


def circuit_from_string(circuit: str) -> QCircuit:
	"""
	Transforms a string from QCircuit.__str__ back into a QCircuit.

	Parameters
	----------
		circuit : str
			A string in the format that QCircuit.__str__ prints it.

			Current supported gates are X, Y, Z, H, Phase, Rx, Ry, Rz and SWAP.

	Returns
	----------
	A QCircuit object representing a circuit.
	"""
	if not validate_circuit_syntax(circuit):
		raise InvalidSyntaxError
	gate_regex = re.compile(
		f'({NP_ONEQ_GATES_REGEX}|{P_ONEQ_GATES_REGEX}|{SWAP_GATE_REGEX})'
	)
	# Finds all invidual gates.
	gates = gate_regex.findall(circuit)
	gates = [gate_string_to_dict(g[0]) for g in gates]
	if not gates:
		return None
	circuit = gate_from_gate_dict(gates[0])
	for gate in gates[1:]:
		circuit += gate_from_gate_dict(gate)
	return circuit
