import spade
import networkx as nx
import copy
from random import  randint
from bin_agent import BinAgent
from truck_agent import TruckAgent
from spade.agent import Agent
from spade.behaviour import CyclicBehaviour
import sys
from spade.message import Message
import asyncio
import time
import json

class Environment(): # 0 = free road, 1 = waste bin, 2 = central, 9 = roadblock
    """
    Represents the physical and logical environment of the simulation.

    Attributes:
        width (int): Grid width (number of columns).        
        height (int): Grid height (number of rows).         
        grid (list): 2D matrix representing the map (0=road, 1=bin, 2=central, 9=block, -1=obstacle).       
        bins (dict): Dictionary mapping positions (x, y) to BinAgent instances.         
        trucks (list): List of active TruckAgent instances.         
        central (tuple): Coordinates (y, x) of the central station.         
        g (networkx.Graph): Graph representation of the road network.       
        start_time (float): Timestamp of the simulation start.      
    """
    def __init__(self, width, height, grid): 
        """
        Initialize the Environment.

        Args:
            width (int): The width of the grid.             
            height (int): The height of the grid.       
            grid (list): The initial layout matrix.         
        """
        self.width = width
        self.height = height
        self.grid = grid  
        self.bins = {}  # coordinate list
        self.trucks = []  
        self.central = (5,5)
        self.grid[5][5] = 2 # place the central station
        self.g = nx.Graph()
        self.convert_to_graph()
        self.start_time = time.time()

    @staticmethod
    def node_name_template(row, col):
        """
        Generate a unique string identifier for a graph node.

        Args:
            row (int): The Y coordinate.        
            col (int): The X coordinate.

        Returns:
            str: A unique name formatted as "x={col} y={row}".
        """
        return "x=" + str(col) + " y=" + str(row) # each cell gets a unique name, facilitating NetworkX usage which works with named nodes
    
    @staticmethod
    def get_pos_from_node_name(nodename):
        """
        Extract coordinates from a node name string.

        Args:
            nodename (str): The node identifier string.

        Returns:
            tuple: The (row, col) coordinates.
        """
        col_str, row_str = nodename.split(" ")
        col = int(col_str.split("=")[1])   # comes from x in the name
        row = int(row_str.split("=")[1])   # comes from y in the name
        return (row,col)

    def expand_aux(self, grid, row, col, dir_x, dir_y):
        """
        Helper method to connect adjacent nodes in the graph.

        Args:
            grid (list): The simulation grid.       
            row (int): Current row.         
            col (int): Current column.      
            dir_x (int): Direction offset for X.        
            dir_y (int): Direction offset for Y.        
        """
        n_col = col + dir_x
        n_row = row + dir_y
        if 0 <= n_col < len(grid[0]) and 0 <= n_row < len(grid):
            if grid[n_row][n_col] <= 2: # creates edges between adjacent nodes (up, down, left, right)
                self.g.add_node(self.node_name_template(n_row, n_col))
                if not self.g.has_edge(self.node_name_template(row, col), self.node_name_template(n_row, n_col)):
                    self.g.add_edge(self.node_name_template(row, col), self.node_name_template(n_row, n_col), weight=1) # standard travel cost = 1
        return

    def expand(self, grid, row, col, dirs):
        """
        Expand connections from a node in specified directions.

        Args:
            grid (list): The simulation grid.       
            row (int): Current row.         
            col (int): Current column.      
            dirs (list): List of direction vectors [[dx, dy], ...].         
        """
        for direct in dirs:
            self.expand_aux(grid, row, col, direct[0], direct[1])
        return

    def convert_to_graph(self):
        """Convert the 2D grid into a NetworkX Graph with nodes and edges for navigable areas."""
        grid = copy.deepcopy(self.grid)
        for row in range(len(grid)):
            for col in range(len(grid[0])):
                if grid[row][col] <= 2:    #any number below or equal to one represents the road or bins(obstacles are ignored)
                    grid[row][col] = -1
                    self.g.add_node(self.node_name_template(row, col))
                    self.expand(grid, row, col, [[1, 0], [-1, 0], [0, 1], [0, -1]])

    # Only stores the new agent names
    async def add_bin(self, position, waste_type="organic"):
        """
        Create and start a new BinAgent at the specified position.

        Args:
            position (tuple): The (x, y) coordinates.       
            waste_type (str, optional): Type of waste. Defaults to "organic".

        Raises:
            ValueError: If position is invalid, occupied, or an obstacle.
        """
        try:
            # Check if position is valid
            if not (0 <= position[0] < self.width and 0 <= position[1] < self.height):
                raise ValueError(f"Position {position} is outside grid boundaries {self.width}x{self.height}")
            
            # Check if it is not an obstacle
            if self.grid[position[1]][position[0]] == -1:
                raise ValueError(f"Position {position} is an obstacle")
            
            if self.grid[position[1]][position[0]] == 9:
                raise ValueError(f"Position {position} is a roadblock")
                
            if position in self.bins:
                raise ValueError(f"Position {position} already has a bin")

            bin_name = f"bin_{waste_type}_{len(self.bins) + 1}@localhost"
            bin_agent = BinAgent(jid=bin_name, password="password", environment=self, 
                            position=(position[1], position[0]), waste_type=waste_type)
            self.bins[position] = bin_agent
            self.grid[position[1]][position[0]] = 1
            print(f"[{bin_agent.name}] {waste_type.capitalize()} bin created at {position}")
            await bin_agent.start(auto_register=True)
            
        except Exception as e:
            print(f" Error creating bin at {position}: {e}")
            raise

    def get_bin_at_position(self, position):
        """
        Retrieve the BinAgent at a specific position.

        Args:
            position (tuple): The (x, y) coordinates.

        Returns:
            BinAgent or None: The agent instance if found, else None.
        """
        return self.bins.get((position[1], position[0]), None)
    
    async def add_truck(self, position, truck_type="organic"):
        """
        Create and start a new TruckAgent at a specific position.

        Args:
            position (tuple): The start (x, y) coordinates.         
            truck_type (str, optional): Type of truck. Defaults to "organic".

        Raises:
            ValueError: If the position is invalid.
        """
        try:
            # Check if position is valid
            if not (0 <= position[0] < self.width and 0 <= position[1] < self.height):
                raise ValueError(f"Position {position} is outside grid boundaries {self.width}x{self.height}")
            
            # Check if it is not an obstacle
            if self.grid[position[1]][position[0]] == -1:
                raise ValueError(f"Position {position} is an obstacle")
                
            if self.grid[position[1]][position[0]] == 9:
                raise ValueError(f"Position {position} is a roadblock")

            truck_name = f"truck_{truck_type}_{len(self.trucks) + 1}@localhost"
            truck_agent = TruckAgent(truck_name, "password", (position[1], position[0]), self, truck_type)
            self.trucks.append(truck_agent)
            print(f"[{truck_agent.name}] {truck_type.capitalize()} truck created at {position}")
            await truck_agent.start(auto_register=True)
            
        except Exception as e:
            print(f"Error creating truck at {position}: {e}")
            raise

    def get_bins_by_type(self, waste_type):
        """
        Get all bins of a specific waste type.

        Args:
            waste_type (str): The waste type to filter by.

        Returns:
            list: A list of BinAgent objects.
        """
        return [bin for bin in self.bins.values() if bin.waste_type == waste_type]
    
    
    def get_trucks_by_type(self, truck_type):
        """
        Get all trucks of a specific type.

        Args:
            truck_type (str): The truck type to filter by.

        Returns:
            list: A list of TruckAgent objects.
        """
        return [truck for truck in self.trucks if truck.truck_type == truck_type]

    def get_all_trucks(self):
        """
        Get a list of all registered trucks.

        Returns:
            list: List of TruckAgent objects.
        """
        return self.trucks

    def move_truck(self, truck, new_position):  # new_position comes as (y, x) = (row, col)
        """
        Update a truck's position in the environment.

        Args:
            truck (TruckAgent): The truck agent to move.        
            new_position (tuple): The new (row, col) coordinates.
        """
        # Verify grid bounds
        if 0 <= new_position[0] < self.height and 0 <= new_position[1] < self.width:
            truck.agent.position = (new_position[0], new_position[1])   # Update the agent
            print(f"[{truck.agent.name}] [{truck.agent.truck_type}] Truck moved to ({new_position[1]},{new_position[0]}).")
            print(f"[{truck.agent.name}] [{truck.agent.truck_type}] Fuel = {truck.agent.fuel}")
        else:
            print(f"[{truck.agent.name}] [{truck.agent.truck_type}] New position out of bounds.")

    def get_nearby_bins(self, position, waste_type=None):
        """
        Find bins close to a given position, ordered by distance.

        Args:
            position (tuple): The reference position (x, y).        
            waste_type (str, optional): Filter by waste type.

        Returns:
            list: A list of nearby BinAgent objects.
        """
        nearby_bins = []
        for bin in self.bins.values():
            # Filter by waste type if specified
            if waste_type and bin.waste_type != waste_type:
                continue
                
            if bin.current_waste >= bin.max_capacity*0.4:
                # Calculate distance (or other proximity criteria)
                distance = abs(bin.position[0] - position[0]) + abs(bin.position[1] - position[1])
                if distance <= 15:  # Exploration radius defined as 15
                    nearby_bins.append((bin, distance))
        sorted_bins = sorted(nearby_bins, key=lambda x: x[1])
        # Returns only the bins, discarding distances
        return [bin for bin, _ in sorted_bins]

    def get_nearby_compatible_bins(self, position, truck_type):
        """
        Get nearby bins compatible with a specific truck type.

        Args:
            position (tuple): Reference position.           
            truck_type (str): Type of the truck (e.g., "organic").

        Returns:
            list: List of compatible BinAgents.
        """
        waste_type = truck_type  # Organic trucks collect organic bins, recyclable trucks collect recyclable bins
        return self.get_nearby_bins(position, waste_type)

    async def add_roadBlock(self, position):
        """
        Add a road block at the specified position, removing graph edges.

        Args:
            position (tuple): The (x, y) coordinates of the blockage.
        """
        self.grid[position[1]][position[0]]=9
        node_name=self.node_name_template(position[1],position[0])
        edges=list(self.g.edges(node_name))
        for edge_name in edges:
            # removes the edge that connects the nodes in edge_name (*edge_name serves to unpack the tuple (node1_name, node2,_name))
            self.g.remove_edge(*edge_name)
        print("ROAD BLOCK CRIADO")
        self.sendEnvironmentUpdate()

    async def remove_roadBlock(self, position):
        """
        Remove a road block and restore graph connections.

        Args:
            position (tuple): The (x, y) coordinates to clear.
        """
        self.grid[position[1]][position[0]]=0
        node_name=self.node_name_template(position[1],position[0])
        adjacent_nodes=[]
        # get valid vertical adjacent nodes
        for i in [-1,1]:
            if(0<=position[1]+i<self.height):
                adjacent_nodes.append(self.node_name_template(position[1]+i,position[0]))
        # get valid horizontal adjacent nodes 
        for i in [-1,1]:
            if(0<=position[0]+i<self.width):
                adjacent_nodes.append(self.node_name_template(position[1],position[0]+i))
        # add all the edges that connect the roadblock node to it's adjacents 
        for adjacent_node in adjacent_nodes:
            self.g.add_edge(node_name, adjacent_node, weight=1)
        self.sendEnvironmentUpdate()

    # level 0 resets al traffic
    async def set_traffic(self, level):
        """
        Apply traffic congestion to the graph edges.
        
        Args:
            level (int): Traffic severity (0 = none, 1-5 = increasing congestion).
        """
        match level:
            case 0:
                edges=list(self.g.edges())
                for edge_name in edges:
                    self.g.edges[edge_name]['weight'] = 1
                return
            case 1:
                percentage=0.3 # percentage of edges affected by traffic
                multiplier=1.5 # how much the edge weight increases, simulating slowness
            case 2:
                percentage=0.3
                multiplier=2
            case 3:
                percentage=0.5
                multiplier=2
            case 4:
                percentage=0.6
                multiplier=2.5
            case 5:
                percentage=0.8
                multiplier=3
            case _:
                print("Invalid level of traffic, no traffic applied")
                return
            
        edges=list(self.g.edges)
        n_edges=int(len(edges)*percentage)

        for _ in range(n_edges):
            idx=randint(0,len(edges)-1) # chooses edges randomly
            edge_name=edges[idx]
            current_weight= self.g.edges[edge_name].get('weight')
            self.g.edges[edge_name]['weight']= int(current_weight*multiplier)
        
        self.sendEnvironmentUpdate() 

    def sendEnvironmentUpdate(self):
        """Flag all trucks that the environment state has changed."""
        for truck in self.trucks:
            truck.changes = True

    def timer (self):
        """
        Get elapsed simulation time.

        Returns:
            int: Seconds since start.
        """
        return int(time.time()-self.start_time)

    def break_truck(self, last_call):
        """
        Randomly cause a truck to break down every 90 seconds.

        Args:
            last_call (int): Timestamp of the last breakdown check.

        Returns:
            int: Updated timestamp.
        """
        cur_time = self.timer()
        if (cur_time > (90 + last_call)) and len(self.trucks) > 0 and randint(0,1) == 1:
            truck = self.trucks[randint(0, len(self.trucks) - 1)]
            truck.is_broken = True # marks as broken
            print(f"[{truck.name}] [{truck.truck_type}] Truck broke down!")
            return self.timer()
        return last_call

    async def start_system(self):
        """Initialize and add default behaviours to all agents."""
        for bin in self.bins.values():
            bin.add_behaviour(bin.WasteAccumulationBehaviour(period=bin.accumulation_period))
        for truck in self.trucks:
            truck.add_behaviour(truck.ExploreEnvironmentBehaviour())

    def update_display(self):
        """
        Gather data for the GUI display.

        Returns:
            tuple: (grid, trucks, bins, traffic_edges)
        """
        # Collect all traffic-affected edges
        traffic_edges = [
        (self.get_pos_from_node_name(edge[0]), self.get_pos_from_node_name(edge[1]))
        for edge in self.g.edges
        if self.g.edges[edge].get('weight', 1) > 1
        ]
        return self.grid, self.trucks, self.bins, traffic_edges

    def get_system_stats(self):
        """
        Calculate system statistics by waste type.

        Returns:
            dict: Nested dictionary with stats for 'organic' and 'recyclable'.
        """
        stats = {
            'organic': {'bins': 0, 'trucks': 0, 'total_waste': 0, 'avg_waste_level': 0},
            'recyclable': {'bins': 0, 'trucks': 0, 'total_waste': 0, 'avg_waste_level': 0}
        }
        
        # Count bins and waste by type
        for bin in self.bins.values():
            if bin.waste_type in stats:
                stats[bin.waste_type]['bins'] += 1
                stats[bin.waste_type]['total_waste'] += bin.current_waste
        
        # Calculate average waste levels
        for waste_type in stats:
            if stats[waste_type]['bins'] > 0:
                stats[waste_type]['avg_waste_level'] = stats[waste_type]['total_waste'] / stats[waste_type]['bins']
        
        # Count trucks by type
        for truck in self.trucks:
            if truck.truck_type in stats:
                stats[truck.truck_type]['trucks'] += 1
        
        return stats

    def print_system_status(self):
        """Print formatted system statistics to the console."""
        stats = self.get_system_stats()
        print("\n=== SYSTEM STATUS ===")
        for waste_type in ['organic', 'recyclable']:
            data = stats[waste_type]
            print(f"{waste_type.capitalize()}:")
            print(f"  Bins: {data['bins']}")
            print(f"  Trucks: {data['trucks']}")
            print(f"  Average waste level: {data['avg_waste_level']:.1f}%")
            print(f"  Total waste: {data['total_waste']} units")
        print("====================\n")

async def load_environment_from_json(file_path):
    """
    Load environment configuration and agents from a JSON file.

    Args:
        file_path (str): Path to the .json configuration file.

    Returns:
        Environment: A fully configured Environment instance.
    """
    with open(file_path, 'r') as f:
        data = json.load(f)

    env_config = data["environment"]
    rows = env_config["rows"]
    cols = env_config["cols"]
    layout = env_config["layout"]

    env = Environment(cols, rows, layout)

    # Traffic from JSON 
    traffic_level = env_config.get("traffic", None)
    if traffic_level is not None:
        print(f"Setting traffic level {traffic_level} from JSON...")
        await env.set_traffic(traffic_level)

    # Central
    if "central" in data:
        central_pos = data["central"]
        env.central = (central_pos[1], central_pos[0])
        env.grid[env.central[0]][env.central[1]] = 2
        print(f"Central set to {env.central}")

    # Roadblocks
    for rb in data.get("roadblocks", []):
        rb_position = (rb[1], rb[0])
        await env.add_roadBlock(rb_position)

    # Bins 
    for b in data.get("bins", []):
        position = (b["position"][1], b["position"][0])
        waste_type = b.get("type", "organic")
        max_capacity = b.get("max_capacity", 100)  # Default value 100

        await env.add_bin(position, waste_type=waste_type)
        bin_agent = env.get_bin_at_position(position)
        if bin_agent:
            bin_agent.max_capacity = max_capacity
            print(f"Bin at ({position[1]},{position[0]}) set to max_capacity: {max_capacity}")

    # Trucks
    for t in data.get("trucks", []):
        position = (t["position"][1], t["position"][0])
        truck_type = t.get("type", "organic")
        max_load = t.get("max_load", 400)  # Default value 400
        max_fuel = t.get("max_fuel", 100)  # Default value 100

        await env.add_truck(position, truck_type=truck_type)
        truck = env.trucks[-1]
        truck.max_load = max_load
        truck.max_fuel = max_fuel
        truck.fuel = max_fuel
        print(f"Truck at ({position[1]},{position[0]}) set to max_load: {max_load}, max_fuel: {max_fuel}")

    print("Environment loaded successfully!")
    return env