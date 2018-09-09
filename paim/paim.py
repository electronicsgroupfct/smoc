# This file is part of PAIM
# Copyright (C) 2018 Miguel Fernandes
#
# PAIM is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# PAIM is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.
"""PAIM main module."""

import os
import sys
import time

from .interface.client import Client
from .optimizer.ga import OptimizerNSGA2
from .util import file
from .util import plot as plt


def load_simulator(client):
    """Load the Cadence simulator before starting the optimization.

    This taks is performed once per run (contrary to the Cadence ADE) that
    loads the simulator everytime we run a simulation, which is very
    inefficient.

    Arguments:
        client {handler} -- client that communicates with the simulator

    Raises:
        Exception -- if the response from the server is not the expected

    Returns:
        dict -- circuit variables
    """
    req = dict(type='loadSimulator', data=None)
    client.send_data(req)
    res = client.recv_data()

    try:
        res_type = res['type']
        data = res['data']
    except KeyError as err:  # if the key does not exist
        print(f"Error: {err}")

    if res_type != 'loadSimulator':
        raise Exception('The response type should be "loadSimulator"!!!')

    return data


def print_paim_summary(current_time, sim_multi, project_dir, project_cfg,
                       optimizer_cfg, objectives, constraints, circuit_vars,
                       checkpoint_load, debug):
    """Print a summary with the project, circuit, and optimizer configurations.

    Arguments:
        current_time {str} -- current date and time
        sim_multi {int} -- number of parallel simulations
        project_dir {str} -- project directory
        project_cfg {dict} -- project configuration parameters
        optimizer_cfg {dict} -- optimizer configuration parameters
        objectives {dict} -- optimization objectives
        constraints {dict} -- optimization constraints
        circuit_vars {dict} -- circuit design variables
        checkpoint_load {str|None} -- checkpoint file to load, if provided
        debug {bool} -- PAIM running mode (debug mode if True)
    """
    running_mode = "debug" if debug else "normal"
    checkpoint_fname = checkpoint_load.split('/')[-1].split(
        '.')[0] if checkpoint_load else "no"

    fname = f"{project_dir}/summary_{current_time}.txt"

    summary = f"""******************************************************
**** PAIM - Python Optimizer for Cadence Virtuoso ****
****************************************************** 
* Running date and time: {current_time}              
* Project name: {project_cfg['project_name']}            
* Project path: {project_cfg['project_path']}        
* Running mode (normal/debug): {running_mode}        
* Running from checkpoint: {checkpoint_fname}        
**************** Optimizer parameters ****************
* Population size: {optimizer_cfg['pop_size']}
* # of generations: {optimizer_cfg['max_gen']}
* # of parallel simulations: {sim_multi}
* Mutation probability: {optimizer_cfg['mut_prob']}
* Crossover probability: {optimizer_cfg['cx_prob']}
* Mutation crouding degree: {optimizer_cfg['mut_eta']}
* Crossover crouding degree: {optimizer_cfg['cx_eta']}
*************** Optimization objectives **************\n"""
    for key, val in objectives.items():
        summary += f"* {key}: {val[0]} [{val[1]}]\n"
    summary += "************** Optimization constraints **************\n"
    for key, val in constraints.items():
        summary += f"* {key}: min = {val[0]}, max = {val[1]}\n"
    summary += "************** Circuit design variables **************\n"
    for key, val in circuit_vars.items():
        summary += f"* {key}: min = {val[0][0]}, max = {val[0][1]} [{val[1]}]\n"
    summary += "******************************************************\n"

    print(summary)

    with open(fname, 'w') as f:
        f.write(summary)


def run_paim(config_file, checkpoint_load, debug):
    """Run PAIM.

    Arguments:
        config_file {str} -- path of configuration file
        checkpoint_load {str|None} -- checkpoint file to load, if provided
        debug {bool} -- PAIM running mode (debug mode if True)

    Raises:
        ValueError -- if the circuit variables don't match with the variables provided
                      in the configuration file
    """
    # Read config file and load the configurations into variables
    paim_cfg = file.read_yaml(config_file)

    if not paim_cfg:  # If config is not valid
        sys.exit("Invalid file name or config...")

    # Start the client
    server_cfg = paim_cfg['server_cfg']
    try:
        print("Connecting to server...")
        client = Client(server_cfg['host'], server_cfg['port'])
    except RuntimeError as err:
        sys.exit("[ClientError] {0}".format(err))

    try:
        print("[INFO] Loading simulator...")
        res_vars, sim_multi = load_simulator(client)

        circuit_vars = paim_cfg['circuit_vars']
        diff = set(circuit_vars.keys()) - set(res_vars.keys())

        if diff:  # If it's not empty (i.e. bool(diff) is True)
            err = "The circuit variables don't match with the variables provided in the file"
            raise ValueError(err)

        # Get the remaining configs
        project_cfg = paim_cfg['project_cfg']
        optimizer_cfg = paim_cfg['optimizer_cfg']
        objectives = paim_cfg['objectives']
        constraints = paim_cfg['constraints']

        # Get current date and time
        current_time = time.strftime("%Y%m%d_%H-%M", time.localtime())

        # Define the checkpoint/logbook/plot file names
        project_dir = f"{project_cfg['project_path']}/{project_cfg['project_name']}"
        checkpoint_dir = project_dir + f"/{project_cfg['checkpoint_path']}"
        checkpoint_fname = checkpoint_dir + f"/{current_time}.pickle"
        logbook_dir = project_dir + f"/{project_cfg['logbook_path']}"
        logbook_fname = logbook_dir + f"/{current_time}.pickle"
        plot_dir = project_dir + f"/{project_cfg['plot_path']}"
        plot_fname = plot_dir + f"/{current_time}.html"

        # Create the required directories, if they do not exist
        if not os.path.exists(project_dir):
            os.makedirs(project_dir)
        if not os.path.exists(checkpoint_dir):
            os.makedirs(checkpoint_dir)
        if not os.path.exists(logbook_dir):
            os.makedirs(logbook_dir)
        if not os.path.exists(plot_dir):
            os.makedirs(plot_dir)

        # Get the verbosity
        verbose = project_cfg['verbose']

        if verbose:
            print_paim_summary(current_time, sim_multi, project_dir,
                               project_cfg, optimizer_cfg, objectives,
                               constraints, circuit_vars, checkpoint_load,
                               debug)

        # Remove the units from the "circuit_vars" and from the "objectives"
        circuit_vars_tmp = {key: val[0] for key, val in circuit_vars.items()}
        objectives_tmp = {key: val[0] for key, val in objectives.items()}

        # Load the optimizer
        paim = OptimizerNSGA2(
            objectives_tmp, constraints, circuit_vars_tmp,
            optimizer_cfg['pop_size'], optimizer_cfg['max_gen'], client,
            optimizer_cfg['mut_prob'], optimizer_cfg['cx_prob'],
            optimizer_cfg['mut_eta'], optimizer_cfg['cx_eta'], debug)

        # Run the GA
        fronts, logbook = paim.run_ga(checkpoint_fname, sim_multi,
                                      checkpoint_load,
                                      optimizer_cfg['checkpoint_freq'],
                                      optimizer_cfg['sel_best'], verbose)

        # Save logbook pickled to file
        file.write_pickle(logbook_fname, logbook)

        # Print statistics
        plt.plot_pareto_fronts(
            fronts, circuit_vars, objectives, plot_fname=plot_fname)

        # End the optimizer
        print("\nShutting down.")
        req = dict(type='info', data='exit')
        client.send_data(req)

    except (RuntimeError, TypeError, ValueError) as err:
        print(f"[Exit with the Error] {err}")

    finally:
        client.close()  # Close the client socket

    print("---- END OF CLIENT ----")