from spade.agent import Agent
from spade.behaviour import CyclicBehaviour
from spade.message import Message
import spade
import asyncio
import networkx as nx
import ast

class TruckAgent(Agent):
    """
    An autonomous agent representing a waste collection truck.

    Attributes:
        environment (Environment): Reference to the simulation environment.         
        truck_type (str): The type of waste the truck collects ("organic" or "recyclable").         
        load (int): Current waste load in the truck.        
        max_load (int): Maximum waste capacity of the truck.        
        fuel (int): Current fuel level.         
        max_fuel (int): Maximum fuel capacity.          
        position (tuple): Current grid coordinates (row, col).          
        is_busy (bool): True if the truck is actively heading to a bin, central, or is dealing with a task.             
        emergency (bool): True if the truck is in an emergency state (low fuel/full load).          
        exploration_bin (BinAgent): The bin currently targeted for collection or assignment.            
        current_path (list | None): List of node names (str) representing the planned route.            
        where (str | None): Indicates the target type ('bin' or 'central').             
        not_accessible_bins (list[tuple]): List of bin positions that are claimed by other trucks or temporarily inaccessible.          
        no_path (list[tuple]): List of bin positions for which no valid path currently exists in the graph.             
        changes (bool): Flag set by the environment to signal graph changes (e.g., traffic, roadblock).             
        is_broken (bool): True if the truck has broken down and is temporarily unavailable.             
        collected_waste (int): Total waste collected over the simulation.           
        total_fuel (int): Total fuel consumed over the simulation.          
        total_distance (int): Total distance traveled (sum of edge weights).            
        collab (int): Number of times the truck was involved in collaboration (negotiation or allocation).      
    """
    def __init__(self, jid, password, position, environment, truck_type="organic"):
        """
        Initialize the Truck Agent.

        Args:
            jid (str): The agent's JID.         
            password (str): The agent's password.       
            position (tuple): The initial location (row, col).      
            environment (obj): The shared environment object.       
            truck_type (str, optional): Type of waste the truck handles. Defaults to "organic".         
        """
        super().__init__(jid, password)
        self.environment = environment
        self.truck_type = truck_type  # "organic" or "recyclable"
        self.load = 0   # Current capacity
        self.max_load = 400  # Default value
        self.fuel = 100   # Current fuel 
        self.max_fuel = 100  # Default value
        
        self.position = position # we always consider position to be (row,col)
        self.is_busy = False   # True if truck is busy going to a bin, False if it has nothing to do
        self.emergency = False
        self.exploration_bin = None  # Target bin during exploration (saves bin)
        self.current_path = None
        self.where = None
        self.not_accessible_bins = []   # Bins claimed by other trucks
        self.no_path = []   # No path for these bins
        self.changes = False
        self.is_broken = False
        self.collected_waste = 0    # Stores total collected waste
        self.total_fuel = 0     # Stores total fuel spent
        self.total_distance = 0    # Stores total distance traveled
        self.collab = 0  # Stores the number of collaborations / allocations

    def get_same_type_trucks(self):
        """
        Get all other trucks in the environment of the same waste type.

        Returns:
            list: List of compatible TruckAgent objects (excluding self).
        """
        return [truck for truck in self.environment.trucks if truck.truck_type == self.truck_type and truck.jid != self.jid]

    def is_waste_type_compatible(self, bin_waste_type):
        """
        Check if the truck can collect the specified type of waste.

        Args:
            bin_waste_type (str): The type of waste in the bin.

        Returns:
            bool: True if compatible, False otherwise.
        """
        return self.truck_type == bin_waste_type

    #waits for cfp messages -> "Contractor" role in Contract Net protocol
    class ReceiveCFPBehaviour(CyclicBehaviour):
        """
        Cyclic Behaviour: Acts as the "Contractor" in CNP, listening for CFP messages.
        """
        async def run(self):
            """
            Receives CFP, checks compatibility, calculates cost/path, and sends PROPOSE or DECLINE.
            """
            msg = await self.receive(timeout=1)
            if msg and msg.metadata.get("performative") == "cfp":
                # Parse bin position and waste type from message body
                parts = msg.body.split(",")
                row, col = map(int, parts[:2])
                bin_waste_type = parts[2] if len(parts) > 2 else "generic"
                bin_location = (row, col)
                
                print(f"📨 [{self.agent.name}] Received CFP from {bin_waste_type} bin at ({col},{row})")
                
                # Check waste type compatibility first
                if not self.agent.is_waste_type_compatible(bin_waste_type):
                    print(f"[{self.agent.name}] Incompatible with {bin_waste_type} bin at ({col},{row})")
                    await self.decline_proposal(msg.sender)
                    return
                    
                if self.agent.is_busy or self.agent.is_broken:
                    print(f"[{self.agent.name}] Busy or broken, rejecting CFP")
                    await self.decline_proposal(msg.sender)
                    return
                
                # Check if nodes exist in graph
                source_node = self.agent.environment.node_name_template(self.agent.position[0], self.agent.position[1])
                target_node = self.agent.environment.node_name_template(bin_location[0], bin_location[1])
                
                if source_node not in self.agent.environment.g:
                    print(f"[{self.agent.name}] Source node {source_node} not in graph")
                    await self.decline_proposal(msg.sender)
                    return
                    
                if target_node not in self.agent.environment.g:
                    print(f" [{self.agent.name}] Target node {target_node} not in graph")
                    await self.decline_proposal(msg.sender)
                    return
                
                # check if it possible to get to the bin
                try:
                    if not nx.has_path(self.agent.environment.g, source_node, target_node):
                        print(f" [{self.agent.name}] No path to bin at ({col},{row})")
                        if bin_location not in self.agent.no_path:
                            self.agent.no_path.append(bin_location)
                            self.agent.not_accessible_bins.append(bin_location)
                        await self.decline_proposal(msg.sender)
                    else:
                        is_possible = self.agent.get_cost(self.agent.position, bin_location) + self.agent.get_cost(bin_location, self.agent.environment.central)
                        if is_possible < self.agent.fuel and not self.agent.is_busy:
                            await self.prepare_proposal(bin_location, msg.sender, bin_waste_type)
                        else:
                            await self.decline_proposal(msg.sender)
                except Exception as e:
                    print(f" [{self.agent.name}] Error checking path: {e}")
                    await self.decline_proposal(msg.sender)
        
        async def decline_proposal(self, bin_jid):
            """
            Send a DECLINE message to the bin's agent.

            Args:
                bin_jid (str): The JID of the bin agent that sent the CFP.
            """
            decline_msg = Message(to = str(bin_jid))
            decline_msg.set_metadata("performative", "decline")
            decline_msg.body = "Truck is busy"
            await self.send(decline_msg)
            print(f"[{self.agent.name}] [{self.agent.truck_type}] Truck rejected the request from {bin_jid} (busy).")
    
        async def prepare_proposal(self, bin_position, bin_jid, bin_waste_type):
            """
            Calculate cost and send a PROPOSE message to the bin.

            Args:
                bin_position (tuple): The (row, col) of the bin.        
                bin_jid (str): The JID of the bin agent.        
                bin_waste_type (str): The type of waste the bin requested.      
            """
            estimated_cost, best_route = self.agent.get_shortest_path(bin_position)
            proposal = Message(to = str(bin_jid))
            proposal.set_metadata("performative", "propose")
            # Include truck type in the proposal
            proposal.body = f"{best_route};{estimated_cost};{self.agent.max_load - self.agent.load};{self.agent.fuel};{self.agent.truck_type}"
            await self.send(proposal)
            print(f"[{self.agent.name}] [{self.agent.truck_type}] Truck sent proposal to {bin_waste_type} bin at ({bin_position[1]},{bin_position[0]}) with cost {estimated_cost}.")

    # newpostion should be (row,col) in other words (y,x)
    def get_shortest_path(self, new_position):
        """
        Calculate the shortest path and its cost from the truck's current position 
        to a target position using Dijkstra's algorithm.

        Args:
            new_position (tuple): The target position (row, col).

        Returns:
            tuple: (cost, path), where cost is the length (weight sum) and path is a list of node names.
        """
        source_node = self.environment.node_name_template(self.position[0], self.position[1])
        target_node = self.environment.node_name_template(new_position[0], new_position[1])

        # path is calculated with the weight attribute of the edges, it includes the source and the target
        path = nx.shortest_path(self.environment.g, source=source_node, target=target_node, method='dijkstra',weight='weight')
        cost = nx.shortest_path_length(self.environment.g, source=source_node, target=target_node, method='dijkstra',weight='weight')
        return (cost, path)
    
    # returns the cost from one point to the other
    def get_cost(self, begin, end):
        """
        Calculate the cost (weighted distance) between two points.

        Args:
            begin (tuple): Starting position (row, col).        
            end (tuple): Ending position (row, col).

        Returns:
            int: The shortest path cost.
        """
        source_node = self.environment.node_name_template(begin[0], begin[1])
        target_node = self.environment.node_name_template(end[0], end[1])
        cost = nx.shortest_path_length(self.environment.g, source=source_node, target=target_node, method='dijkstra',weight='weight')
        return cost

    # reacts to an "accept" message -> meaning, chosen by a bin to collect -> implements "Contract Winner"
    class ReceiveAcceptanceBehaviour(CyclicBehaviour): 
        """Cyclic Behaviour: Implements the "Contract Winner" logic, reacting to ACCEPT messages."""
        async def run(self):
            """Handles ACCEPT message: sets the path, marks busy, and possibly cancels exploration."""
            msg = await self.receive(timeout = 1)
            if msg and msg.metadata.get("performative") == "accept":
                if not self.agent.is_broken and not self.agent.emergency and not self.agent.is_busy:
                    # If an accept message is received, cancel the exploration
                    if self.agent.exploration_bin != None:
                        await self.send_release_message(self.agent.exploration_bin.position)
                    self.agent.is_busy = True
                    self.agent.current_path = ast.literal_eval(msg.body)
                    bin_pos = self.agent.environment.get_pos_from_node_name(self.agent.current_path[-1])
                    bin = self.agent.environment.get_bin_at_position(bin_pos)
                    self.agent.exploration_bin = bin
                    self.agent.where = "bin"
                    
                    # MARKS ON THE BIN THAT THIS COLLECTION IS BY CFP
                    if bin:
                        bin.last_collection_type = 'cfp'
                    
                    print(f"[{self.agent.name}] [{self.agent.truck_type}] Received accept message of CFP. Moving to assigned bin.")
                    #await self.send_claim_message(bin, self.agent.get_cost(self.agent.position, bin_pos))
                else: # if it cannot accept (e.g., broken)
                    path = ast.literal_eval(msg.body)
                    pos = self.agent.environment.get_pos_from_node_name(path[-1])
                    await self.warn_bin(pos) # warns the bin
                    await self.alocate_others_trucks(pos) 

    # the bin gets to know the chosen truck cannot come -> bin acts with "ReceiveProblemBehaviour"
        async def warn_bin(self, pos):
            """
            Send a 'problem' message to the bin, informing it of failure (e.g., breakdown).

            Args:
                pos (tuple): Position of the bin to warn (row, col).
            """
            warn_msg = Message()
            warn_msg.set_metadata("performative", "problem")
            bin = self.agent.environment.get_bin_at_position(pos)
            warn_msg.to = str(bin.jid)
            await self.send(warn_msg)
            print(f"[{self.agent.name}] [{self.agent.truck_type}] Can't go to bin ({bin.position[1]},{bin.position[0]}). Bin warned.")

        # "I cannot collect waste from bin (x,y). Can any other truck take the task for me?"
        async def alocate_others_trucks(self, bin_position):
            """
            Send an 'allocate-task' message to compatible peer trucks, asking for assistance.

            Args:
                bin_position (tuple): Position of the bin that needs collection (row, col).
            """
            print("Entrou em alocate")
            allocate_task_msg = Message()
            allocate_task_msg.set_metadata("performative", "allocate-task") # allocates task to another truck here
            allocate_task_msg.body=f"{bin_position[0]},{bin_position[1]}"
            # Only send to trucks of the same type
            for truck in self.agent.get_same_type_trucks():
                allocate_task_msg.to = str(truck.jid)
                await self.send(allocate_task_msg)
                print(f"[{self.agent.name}] [{self.agent.truck_type}] Asking [{allocate_task_msg.to}] to go to the bin ({bin_position[1]},{bin_position[0]}).")
        
        # Send claim message to all trucks of the same type
        async def send_claim_message(self, bin, cost):
            """
            Send a 'claim-bin' message to peer trucks after a successful CNP acceptance.
            
            Args:
                bin (BinAgent): The bin agent being claimed.        
                cost (int): The cost (weighted distance) to reach the bin.
            """
            claim_msg = Message()
            claim_msg.set_metadata("performative", "claim-bin")
            claim_msg.body = f"{bin.position[0]},{bin.position[1]},{cost},{self.agent.fuel},{self.agent.max_load - self.agent.load},{self.agent.truck_type}"
            for truck in self.agent.get_same_type_trucks():
                claim_msg.to = str(truck.jid)
                await self.send(claim_msg)
                print(f"[{self.agent.name}] [{self.agent.truck_type}] Sent claim message for bin at ({bin.position[1]},{bin.position[0]}) to {truck.jid} due to CFP acceptance.")

        # Send release message to all trucks of the same type
        async def send_release_message(self, bin_position):
            """
            Send a 'release-bin' message to peer trucks, typically when cancelling a collection.
            
            Args:
                bin_position (tuple): The position (row, col) of the bin being released.
            """
            release_msg = Message()
            release_msg.set_metadata("performative", "release-bin")
            release_msg.body = f"{bin_position[0]},{bin_position[1]}"
            for truck in self.agent.get_same_type_trucks():
                release_msg.to = str(truck.jid)
                await self.send(release_msg)
            print(f"[{self.agent.name}] [{self.agent.truck_type}] Sent release message for bin at ({bin_position[1]},{bin_position[0]}).")

    # proactive/autonomous behavior -> truck doesn't need to wait for orders
    class ExploreEnvironmentBehaviour(CyclicBehaviour):
        """Implements the truck's autonomous and proactive exploration logic. """
        async def run(self):
            """Searches for bins and attempts to claim the best one for autonomous collection."""
            if not self.agent.is_busy and not self.agent.emergency and not self.agent.is_broken and self.agent.exploration_bin == None: # when the truck is free
                self.agent.current_path = None
                nearby_bins = self.agent.environment.get_nearby_bins(self.agent.position) # looks for nearby bins
                for bin in nearby_bins: # for each nearby bin
                    # Check waste type compatibility
                    if not self.agent.is_waste_type_compatible(bin.waste_type):
                        continue
                        
                    if bin.position not in self.agent.not_accessible_bins and not self.agent.is_busy and not self.agent.is_broken:
                        try: 
                            cost, path = self.agent.get_shortest_path(bin.position) # calculates the path
                            self.agent.exploration_bin = bin
                            self.agent.where = 'bin'
                            if (not self.agent.is_busy and not self.agent.is_broken):
                                await self.send_claim_message(bin, cost) # sends claim bin
                                print(f"[{self.agent.name}] [{self.agent.truck_type}] Waiting for responses after claiming {bin.waste_type} bin at ({bin.position[1]},{bin.position[0]}) for EXPLORATION.")
                                await asyncio.sleep(2)  # Waits for responses
                            if not self.agent.is_busy and not self.agent.emergency and not self.agent.is_broken and bin.position not in self.agent.not_accessible_bins:
                                print(f"[{self.agent.name}] [{self.agent.truck_type}] Selected {bin.waste_type} bin at ({bin.position[1]},{bin.position[0]}) for exploration.")
                                
                                # MARKS ON THE BIN THAT THIS COLLECTION IS AUTONOMOUS
                                bin.last_collection_type = 'autonomous'
                                
                                self.agent.current_path = path
                                break

                            else:
                                print(f"[{self.agent.name}] [{self.agent.truck_type}] {bin.waste_type} bin at ({bin.position[1]},{bin.position[0]}) was declined for exploration.") # otherwise, gives up and tries another
                                if not self.agent.is_busy and not self.agent.emergency:
                                    self.agent.exploration_bin = None
                                    self.agent.where = None
                                    self.agent.current_path = None
                                break
                        except Exception as e:
                            print(f"[{self.agent}] [{self.agent.truck_type}] Não exite caminho para o {bin.waste_type} bin ({bin.position[1]},{bin.position[0]})")
                            self.agent.exploration_bin = None
                            self.agent.where = None
                            self.agent.current_path = None
                            self.agent.not_accessible_bins.append(bin.position)
                            self.agent.no_path.append(bin.position)
                                
        async def send_claim_message(self, bin, cost):
            """
            Send a 'claim-bin' message to all trucks of the same type during autonomous exploration.

            Args:
                bin (BinAgent): The bin agent being claimed.        
                cost (int): The cost to reach the bin.
            """
            claim_msg = Message()
            claim_msg.set_metadata("performative", "claim-bin")
            claim_msg.body = f"{bin.position[0]},{bin.position[1]},{cost},{self.agent.fuel},{self.agent.max_load - self.agent.load},{self.agent.truck_type}"
            for truck in self.agent.get_same_type_trucks():
                claim_msg.to = str(truck.jid)
                await self.send(claim_msg)
                print(f"[{self.agent.name}] [{self.agent.truck_type}] Sent claim message for {bin.waste_type} bin at ({bin.position[1]},{bin.position[0]}) to {truck.jid} due to EXPLORATION.")

    # truck receives a "claim-bin" from another truck -> prevents two trucks collecting the same bin
    class ReceiveClaimBehaviour(CyclicBehaviour):
        """Handles incoming 'claim-bin' messages from peers to prevent redundant collections."""
        async def run(self):
            """Negotiates claims based on capacity, cost, fuel, and ID."""
            msg = await self.receive(timeout=1)
            if msg and msg.metadata.get("performative") == "claim-bin" and not self.agent.is_broken and not self.agent.emergency:
                bin_data = msg.body.split(",")
                bin_position = (int(bin_data[0]), int(bin_data[1]))
                other_cost = int(bin_data[2])
                other_fuel = int(bin_data[3])
                other_capacity = int(bin_data[4])
                other_truck_type = bin_data[5] if len(bin_data) > 5 else "organic"
                print(f"[{self.agent.name}] [{self.agent.truck_type}] recebeu claim-bin de [{msg.sender}] ({other_truck_type})")

                # Only respond to trucks of the same type
                if other_truck_type != self.agent.truck_type:
                    return

                # Case 1: this truck also has the same bin as target and is already working on it (is_busy) 
                if self.agent.exploration_bin != None and self.agent.exploration_bin.position == bin_position and self.agent.is_busy:
                    confirm_msg = Message(to=str(msg.sender))
                    confirm_msg.set_metadata("performative", "decline-claim") # message "this bin is mine, I am coming to get it"
                    confirm_msg.body = f"{bin_position[0]},{bin_position[1]}"
                    print(f"[{self.agent.name}] [{self.agent.truck_type}] Warning other truck {msg.sender} to realise claim for bin at ({bin_position[1]},{bin_position[0]}). (My bin)")
                    await self.send(confirm_msg)
                
                # Case 2: they want the same bin but this truck is free
                elif self.agent.exploration_bin != None and self.agent.exploration_bin.position == bin_position and not self.agent.is_broken and not self.agent.is_busy:
                    self.agent.collab += 1
                    print(f"[{self.agent.name}] [{self.agent.truck_type}] avaliando...")
                    my_cost = self.agent.get_cost(self.agent.position, bin_position) # calculates cost
                    my_fuel = self.agent.fuel # fuel
                    my_capacity = self.agent.max_load - self.agent.load # capacity

                    # Deterministic negotiation logic
                    my_id = self.agent.jid
                    other_id = str(msg.sender)
                    negotiate = self.evaluate_negotiation( # compare both trucks
                        my_cost, other_cost, my_fuel, other_fuel,
                        my_capacity, other_capacity,
                        my_id, other_id
                    )

                    if negotiate:  # Other truck is better and will win, this one gives up the bin
                        print(f"[{self.agent.name}] [{self.agent.truck_type}] Realise claim for bin ({bin_position[1]},{bin_position[0]}) to {msg.sender}. (Someone else's bin)")
                        self.agent.exploration_bin = None
                        self.agent.where = None
                        self.agent.current_path = None
                        self.agent.is_busy = False
                        self.agent.not_accessible_bins.append(bin_position)
                    else:
                        # This truck keeps the claim and informs the other truck must yield the bin (decline-claim)
                        confirm_msg = Message(to=str(msg.sender))
                        confirm_msg.set_metadata("performative", "decline-claim")
                        confirm_msg.body = f"{bin_position[0]},{bin_position[1]}"
                        print(f"[{self.agent.name}] [{self.agent.truck_type}] Warning other truck {msg.sender} to realise claim for bin at ({bin_position[1]},{bin_position[0]}). (My bin)")
                        await self.send(confirm_msg)
                # Case 3: they don't want the same bin, just adds to non-accessible list to avoid wasting time
                else:
                    self.agent.not_accessible_bins.append(bin_position)
                    print(f"[{self.agent.name}] [{self.agent.truck_type}] apenas adicionou ({bin_position[1]},{bin_position[0]}) à lista de não acessiveis")

        def evaluate_negotiation(self, my_cost, other_cost, my_fuel, other_fuel, my_capacity, other_capacity, my_id, other_id):
            """
            Deterministic logic to decide which truck should handle the collection based on capacity, cost, fuel and ID.

            Args:
                my_cost (int): Cost for self to reach the bin.      
                other_cost (int): Cost for the peer truck to reach the bin.         
                my_fuel (int): Current fuel of self.        
                other_fuel (int): Current fuel of the peer truck.       
                my_capacity (int): Available capacity of self.      
                other_capacity (int): Available capacity of the peer truck.         
                my_id (str): JID of self.       
                other_id (str): JID of the peer truck.
            
            Returns:
                bool: True if the *other* truck wins the negotiation (meaning self should yield), False otherwise.
            """
            print(f"[{self.agent.jid}] [{self.agent.truck_type}] Negotiation details:")
            print(f"  My cost: {my_cost}, Other cost: {other_cost}")
            print(f"  My fuel: {my_fuel}, Other fuel: {other_fuel}")
            print(f"  My capacity: {my_capacity}, Other capacity: {other_capacity}")
            print(f"  My ID: {my_id}, Other ID: {other_id}")

            # Priority 1: Truck with higher available capacity
            if my_capacity > other_capacity:
                print("[Decision] I have higher capacity.")
                return False
            elif my_capacity < other_capacity:
                print("[Decision] Other has higher capacity.")
                return True

            # Priority 2: Truck with lower cost
            if my_cost < other_cost:
                print("[Decision] I have lower cost.")
                return False
            elif my_cost > other_cost:
                print("[Decision] Other has lower cost.")
                return True

            # Priority 3: Truck with more fuel
            if my_fuel > other_fuel:
                print("[Decision] I have more fuel.")
                return False
            elif my_fuel < other_fuel:
                print("[Decision] Other has more fuel.")
                return True

            # Priority 4: Deterministic tie-breaker by ID
            if str(my_id) < str(other_id):
                print("[Decision] I win by ID.")
                return False
            else:
                print("[Decision] Other wins by ID.")
                return True

    # Receives an "allocate-task" -> due to being broken or incapable -> this is the side receiving the help request
    class ReceiveAllocatationBehaviour(CyclicBehaviour):
        """Handles incoming 'allocate-task' messages, taking over collections from failing or incapable peer trucks."""
        async def run(self):
            """Checks if capable of handling the allocated task and attempts to claim it."""
            msg = await self.receive(timeout = 1)
            if msg and msg.metadata.get("performative") == "allocate-task":
                bin_pos = tuple(map(int, msg.body.split(","))) # problematic bin position
                bin = self.agent.environment.get_bin_at_position(bin_pos)
                
                # Check waste type compatibility
                if bin and not self.agent.is_waste_type_compatible(bin.waste_type):
                    print(f"[{self.agent.name}] [{self.agent.truck_type}] Rejecting allocation for {bin.waste_type} bin at ({bin_pos[1]},{bin_pos[0]}) - incompatible types")
                    return
                
                # if it passes here, it means it can take the job
                if not self.agent.is_busy and not self.agent.emergency and not self.agent.is_broken and not bin_pos in self.agent.no_path:
                    if (self.agent.exploration_bin != None): # release the bin it was exploring, sends release-bin message
                        await self.send_release_message(self.agent.exploration_bin.position)
                    self.agent.current_path = None
                    self.agent.exploration_bin = self.agent.environment.get_bin_at_position(bin_pos)
                    self.agent.where = "bin"
                    self.agent.is_busy = True # sets new target bin and indicates it is busy
                    for truck in self.agent.get_same_type_trucks():
                        await self.warn_bin(bin_pos) # warns the bin that someone is coming to resolve the problem, activates "ReceiveProblemResolveBehaviour" in the bin which stops asking for help
                        await self.prepare_proposal(truck.jid, bin_pos) # sends a claim bin
                    await asyncio.sleep(2)  # Waits for responses
                    if bin_pos not in self.agent.not_accessible_bins: # if no one else claims the same bin (not in non-accessibles) then the truck officially assumes the task
                        print(f"[{self.agent.name}] [{self.agent.truck_type}] Selected bin at ({bin_pos[1]},{bin_pos[0]}) for resolve ALLOCATION problem.")
                        _, self.agent.current_path = self.agent.get_shortest_path(bin_pos)
                        self.agent.collab += 1

        # Send release message to all trucks of the same type
        async def send_release_message(self, bin_position):
            """
            Send a 'release-bin' message to peers when cancelling the current exploration target.
            
            Args:
                bin_position (tuple): The position (row, col) of the bin being released.
            """
            release_msg = Message()
            release_msg.set_metadata("performative", "release-bin")
            release_msg.body = f"{bin_position[0]},{bin_position[1]}"
            for truck in self.agent.get_same_type_trucks():
                release_msg.to = str(truck.jid)
                await self.send(release_msg)
            print(f"[{self.agent.name}] [{self.agent.truck_type}] Sent release message for bin at ({bin_position[1]},{bin_position[0]}).")

        async def warn_bin(self, pos):
            """
            Send a 'resolve-problem' message to the bin, confirming a truck is taking over.
            
            Args:
                pos (tuple): Position of the bin to warn (row, col).
            """
            warn_msg = Message()
            warn_msg.set_metadata("performative", "resolve-problem")
            bin = self.agent.environment.get_bin_at_position(pos)
            warn_msg.to = str(bin.jid)
            await self.send(warn_msg)
            print(f"[{self.agent.name}] [{self.agent.truck_type}] Há um truck interessado no bin com problema")

        async def prepare_proposal(self, truck_name, bin_pos):
            """Send a 'claim-bin' message to peer trucks to claim the allocated task."""
            cost, _ = self.agent.get_shortest_path(bin_pos)
            proposal = Message()
            proposal.set_metadata("performative", "claim-bin")
            proposal.body = f"{bin_pos[0]},{bin_pos[1]},{cost},{self.agent.fuel},{self.agent.max_load - self.agent.load},{self.agent.truck_type}"
            proposal.to = str(truck_name)
            await self.send(proposal)
            print(f"[{self.agent.name}] [{self.agent.truck_type}] Truck sent ALLOCATION claim bin at {bin_pos} with cost {cost}.")

    # receives a release from a truck                  
    class ReceiveReleaseBehaviour(CyclicBehaviour):
        """ Handles incoming 'release-bin' messages from peers."""
        async def run(self):
            """Removes the released bin from the list of non-accessible bins, making it available again."""
            msg = await self.receive(timeout = 1)
            if msg and msg.metadata.get("performative") == "release-bin":
                released_bin = tuple(map(int, msg.body.split(",")))
                # if it was in non-accessible bins, remove it
                if released_bin in self.agent.not_accessible_bins:
                    self.agent.not_accessible_bins.remove(released_bin)

    # receives a decline from a truck -> another truck told this one it can't have the bin because it's already taken
    class ReceiveDeclineClaimBehaviour(CyclicBehaviour):
        """Handles 'decline-claim' messages, yielding the contested bin."""
        async def run(self):
            """If the bin being claimed by this agent is declined, the agent resets its state and marks the bin as inaccessible."""
            msg = await self.receive(timeout=1)
            if msg and msg.metadata.get("performative") == "decline-claim":
                bin_position = tuple(map(int, msg.body.split(",")[:2]))
                print(f"[{self.agent.name}] [{self.agent.truck_type}] Received decline-claim for bin at ({bin_position[1]},{bin_position[0]}) from [{msg.sender}].")
                if self.agent.exploration_bin != None and self.agent.exploration_bin.position == bin_position:
                    self.agent.exploration_bin = None
                    self.agent.where = None
                    self.agent.current_path = None
                    self.agent.is_busy = False
                    print(f"[{self.agent.name}] [{self.agent.truck_type}] Released bin at ({bin_position[1]},{bin_position[0]}) after decline-claim.")
                self.agent.not_accessible_bins.append(bin_position)

    # self-monitoring behavior
    class CheckStatusBehaviour(CyclicBehaviour): 
        """Monitors the truck's fuel and load status for emergency returns."""
        async def run(self):
            """Checks for low fuel or full load (90%) and triggers an emergency return to central."""
            if not self.agent.emergency and not self.agent.is_broken:
                if not self.agent.has_enough_fuel(): # if it has less fuel than cost to central
                    print(f"[{self.agent.name}] [{self.agent.truck_type}] Low fuel. Returning to central.")
                    self.agent.is_busy = True
                    self.agent.emergency = True
                    if (self.agent.exploration_bin != None): # if it has an associated bin, sends release
                        self.send_release_message(self.agent.exploration_bin.position)
                        self.agent.exploration_bin = None
                        self.agent.where = None 
                        self.agent.current_path = None
                    await self.return_to_central()
                elif self.agent.is_full(): # if load is full (90%)
                    print(f"[{self.agent.name}] [{self.agent.truck_type}] Full load. Returning to central.")
                    self.agent.is_busy = True
                    self.agent.emergency = True
                    if (self.agent.exploration_bin != None): # if it has an associated bin, sends release
                        self.send_release_message(self.agent.exploration_bin.position)
                        self.agent.exploration_bin = None
                        self.agent.where = None
                        self.agent.current_path = None
                    await self.return_to_central()

        async def return_to_central(self):
            """Sets the truck's path to the central station and marks its destination."""
            print(f"[{self.agent.name}] [{self.agent.truck_type}] Returning to central at {self.agent.environment.central}.")
            _, self.agent.current_path = self.agent.get_shortest_path(self.agent.environment.central)
            self.agent.where = 'central'
            
        # Send release message to all trucks of the same type
        async def send_release_message(self, bin_position):
            """
            Sends a 'release-bin' message when abandoning a collection for emergency.
            
            Args:
                bin_position (tuple): The position (row, col) of the bin being released.
            """
            release_msg = Message()
            release_msg.set_metadata("performative", "release-bin")
            release_msg.body = f"{bin_position[0]},{bin_position[1]}"
            for truck in self.agent.get_same_type_trucks():
                release_msg.to = str(truck.jid)
                await self.send(release_msg)
            print(f"[{self.agent.name}] [{self.agent.truck_type}] Sent release message for bin at ({bin_position[1]},{bin_position[0]}). Going back to central")

    def has_enough_fuel(self):
        """
        Check if the truck has sufficient fuel to reach the central station.

        Returns:
            bool: True if fuel is greater than the cost to the central, False otherwise.
        """
        cost, _ = self.get_shortest_path(self.environment.central)
        return self.fuel > cost

    def is_full(self):
        """
        Check if the truck's load is 90% or more of its maximum capacity.

        Returns:
            bool: True if the truck is nearly full, False otherwise.
        """
        return self.load >= 0.9 * self.max_load

    class MoveToBehaviour(CyclicBehaviour):
        """Handles the physical movement of the truck along its planned path."""
        async def run(self):
            """Moves the truck one step along the path, consumes fuel, and handles environmental changes."""
            # in each iteration, checks truck state
            if self.agent.changes == True: # if changed, meaning environment updated somehow, checks if route needs changing
                await self.receive_environment_update()
            elif self.agent.is_broken == True: # if broken down
                await self.broke_down()
            else: # if not broken and environment didn't change
                if self.agent.current_path != None:
                    if self.agent.current_path == None:
                        return
                    path = self.agent.current_path
                    if len(self.agent.current_path) != 1:
                        curr_node_name = path[0] # truck moves from node to node
                        next_node_name = path[1]
                        next_pos = self.agent.environment.get_pos_from_node_name(next_node_name)
                        self.agent.environment.move_truck(self, next_pos)
                        edge_data = self.agent.environment.g.get_edge_data(curr_node_name, next_node_name)
                        w_edge = edge_data["weight"] # consumes fuel
                        self.agent.fuel -= w_edge
                        self.agent.total_fuel += w_edge
                        self.agent.total_distance += 1
                        await asyncio.sleep(w_edge) # simulates physical travel time
                        if self.agent.current_path != None and len(self.agent.current_path) != 1 and next_node_name == self.agent.current_path[1]:
                            self.agent.current_path = self.agent.current_path[1:] # cuts the node representing where the truck just left
                            print("cut path")
                    else:
                        print("Chegou ao destino") # if path has only 1 node
                        if self.agent.where == 'bin': # if destination is a bin
                            print("vai coletar lixo?")
                            await self.collect_waste() # collects waste
                            self.agent.current_path = None
                            self.agent.exploration_bin = None
                            self.agent.where = None
                            self.agent.is_busy = False
                        elif self.agent.where == 'central': # if destination is central
                            print("vai dar refill?")
                            await self.refill()
                            self.agent.current_path = None
                            self.agent.exploration_bin = None
                            self.agent.where = None
                            self.agent.is_busy = False
        
        async def receive_environment_update(self):
            """Handles changes in the environment (e.g., traffic or roadblocks)."""
            # Reset change flag
            self.agent.changes = False

            # Checks if previously inaccessible bins now have a path
            for bin_pos in list(self.agent.no_path):
                try:
                    _, p = self.agent.get_shortest_path(bin_pos)
                    self.agent.no_path.remove(bin_pos)
                    self.agent.not_accessible_bins.remove(bin_pos)
                except Exception:
                    pass  # still no path

            # Recalculates current path with updated traffic
            if hasattr(self.agent, "current_target") and self.agent.current_target is not None:
                try:
                    _, new_path = self.agent.get_shortest_path(self.agent.current_target)
                    self.agent.current_path = new_path
                except Exception:
                    pass  # if fails, keeps old path

                    
                    # Check if truck's current path is still valid
                    if self.agent.current_path != None: # current_path is the truck's path in the graph (a list of nodes)
                        path = self.agent.current_path
                        self.agent.current_path = None
                        final_pos = self.agent.environment.get_pos_from_node_name(path[-1]) # path[-1] is the last node (the bin)
                        try: # tries to recalculate path to destination
                            _, new_path = self.agent.get_shortest_path(final_pos) # if successful, replaces old path
                            self.agent.current_path = new_path
                        except Exception as e: # if path to destination no longer exists
                                    print(f"[{self.agent.name}] [{self.agent.truck_type}] Mudanças na estrada. Já não exite caminho para o bin em ({final_pos[1]},{final_pos[0]})")
                                    self.agent.exploration_bin = None
                                    self.agent.where = None
                                    self.agent.not_accessible_bins.append(final_pos)
                                    self.agent.no_path.append(final_pos)
                                    self.agent.current_path = None
                                    self.agent.is_busy = False
                                    # Now we must tell the bin I am not coming
                                    await self.warn_bin(final_pos)
        
        async def warn_bin(self, pos):
            """
            Sends a 'problem' message to the target bin when the path is lost due to environment changes.
            
            Args:
                pos (tuple): Position of the bin to warn (row, col).
            """
            warn_msg = Message()
            warn_msg.set_metadata("performative", "problem")
            bin = self.agent.environment.get_bin_at_position(pos)
            warn_msg.to = str(bin.jid)
            await self.send(warn_msg)
            print(f"[{self.agent.name}] [{self.agent.truck_type}] Can't go to bin ({bin.position[1]},{bin.position[0]}). Bin warned.")

        async def collect_waste(self):
            """Simulates waste collection, updating truck load and bin waste level."""
            bin_at_position = self.agent.environment.get_bin_at_position(self.agent.position)
            if bin_at_position:
                load_to_collect = min(bin_at_position.current_waste, self.agent.max_load - self.agent.load)
                self.agent.load += load_to_collect
                self.agent.collected_waste += load_to_collect
                bin_at_position.current_waste -= load_to_collect
                bin_at_position.is_waiting_for_truck = False
                
                # Ensure the bin knows this is an exploration collection if it wasn't by CFP
                if bin_at_position.last_collection_type != 'cfp':
                    bin_at_position.last_collection_type = 'autonomous'
                
                print(f"[{self.agent.name}] [{self.agent.truck_type}] Truck collected {load_to_collect} waste. Current load: {self.agent.load}/{self.agent.max_load}.")
                await self.send_release_message(bin_at_position.position)
            else:
                print(f"[{self.agent.name}] [{self.agent.truck_type}] No bin found at the current position.")
                
        async def refill(self):
            """Simulates refuelling and unloading the waste load at the central station."""
            self.agent.fuel = self.agent.max_fuel  # Simulates refueling
            self.agent.load = 0  # Simulates waste unloading
            await asyncio.sleep(5)
            self.agent.is_busy = False
            self.agent.emergency = False # becomes ready for new tasks
            print(f"[{self.agent.name}] [{self.agent.truck_type}] Refilled and unloaded at central.")

        async def broke_down(self):
            """ Handles the truck breaking down, releasing the bin and entering a waiting state."""
            if (self.agent.is_broken):  
                print(f"[{self.agent.name}] [{self.agent.truck_type}] is broken")   
                if self.agent.current_path != None:   
                    bin_pos = self.agent.environment.get_pos_from_node_name(self.agent.current_path[-1])
                    await self.send_release_message(bin_pos)
                    if (self.agent.is_busy and not self.agent.emergency and self.agent.exploration_bin != None):
                        print("Estava busy,  alocar outros trucks")
                        await self.warn_bin(bin_pos)
                        await self.alocate_others_trucks(bin_pos)
                        
                self.agent.exploration_bin = None
                self.agent.current_path = None
                self.agent.where = None
                
                # Time the truck will stay non-functional
                broken_time = 10
                for i in range (broken_time):
                    await asyncio.sleep(1)
                    print(f"[{self.agent.name}] [{self.agent.truck_type}] {broken_time-i} seconds left until normal functionning")
                print(f"[{self.agent.name}] [{self.agent.truck_type}] normal functioning started") # back to normal
                
                self.agent.emergency = False
                self.agent.is_broken = False
                self.agent.is_busy = False

        async def alocate_others_trucks(self, bin_position):
            """
            Sends an 'allocate-task' message to peers when self breaks down while busy.
            
            Args:
                bin_position (tuple): Position of the bin that needs collection (row, col).
            """
            allocate_task_msg = Message()
            allocate_task_msg.set_metadata("performative", "allocate-task")
            allocate_task_msg.body = f"{bin_position[0]},{bin_position[1]}"
            for truck in self.agent.get_same_type_trucks():
                allocate_task_msg.to = str(truck.jid)
                await self.send(allocate_task_msg)
                print(f"[{self.agent.name}] [{self.agent.truck_type}] broke down. Asking [{allocate_task_msg.to}] to go to the bin ({bin_position[1]},{bin_position[0]}).")

        async def send_release_message(self, bin_position):
            """
            Sends a 'release-bin' message to all trucks of the same type when abandoning a bin due to breakdown.
            
            Args:
                bin_position (tuple): The position (row, col) of the bin being released.
            """
            release_msg = Message()
            release_msg.set_metadata("performative", "release-bin")
            release_msg.body = f"{bin_position[0]},{bin_position[1]}"
            for truck in self.agent.get_same_type_trucks():
                release_msg.to = str(truck.jid)
                await self.send(release_msg)
            
            # Mostrar coordenadas corretas (row, col) sem inverter
            print(f"[{self.agent.name}] [{self.agent.truck_type}] Sent release message for bin at ({bin_position[1]},{bin_position[0]}).")

    class Help(CyclicBehaviour):
        """ Safety mechanism to detect if the truck is stuck or blocked.
        
        If the truck is busy but stationary for too long (5s), it releases the bin, 
        sends a warning to peer trucks, and becomes available again.
        """
        async def run(self):      
            """Monitors truck position over time and triggers alert if the truck is blocked while busy."""                                                              
            # Help only acts if truck is busy and not broken...
            if self.agent.is_busy and not self.agent.is_broken:
                start_pos = self.agent.position
                start_time = self.agent.environment.timer()

                # Waits 5 time units (simulates periodic monitoring)
                await asyncio.sleep(5)
                new_time = self.agent.environment.timer()

                # If enough time passed and truck didn't move -> blocked
                if new_time - start_time >= 5 and self.agent.position == start_pos:
                    print(f"[{self.agent.name}] [{self.agent.truck_type}] parece estar preso. Ativando HELP...")

                    # If associated with a bin, notifies and releases
                    if self.agent.exploration_bin is not None:
                        await self.warn_bin(self.agent.exploration_bin.position)
                        await self.send_release_message(self.agent.exploration_bin.position)
                        print(f"[{self.agent.name}] [{self.agent.truck_type}] liberou o bin e enviou alerta.")

                    # Reset dos estados principais
                    self.agent.is_busy = False
                    self.agent.current_path = None
                    self.agent.exploration_bin = None
                    self.agent.where = None

                    print(f"[{self.agent.name}] [{self.agent.truck_type}] ready for new tasks after HELP.")

    
        
        async def warn_bin(self, pos):
            """
            Sends a 'problem' message to the bin when the truck is stuck.
            
            Args:
                pos (tuple): Position of the bin to warn (row, col).
            """
            warn_msg = Message()
            warn_msg.set_metadata("performative", "problem")
            bin = self.agent.environment.get_bin_at_position(pos)
            warn_msg.to = str(bin.jid)
            await self.send(warn_msg)
            print(f"--------------- [{self.agent.name}] [{self.agent.truck_type}] Can't go to bin ({bin.position[1]},{bin.position[0]}). Bin warned. ---------------")
        
        async def send_release_message(self, bin_position):
            """
            Sends a 'release-bin' message to peers.
            
            Args:
                bin_position (tuple): The position (row, col) of the bin being released.
            """
            release_msg = Message()
            release_msg.set_metadata("performative", "release-bin")
            release_msg.body = f"{bin_position[0]},{bin_position[1]}"
            for truck in self.agent.get_same_type_trucks():
                release_msg.to = str(truck.jid)
                await self.send(release_msg)
            
            # Mostrar coordenadas corretas (row, col) sem inverter
            print(f"--------------- [{self.agent.name}] [{self.agent.truck_type}] Sent release message for bin at ({bin_position[1]},{bin_position[0]}). ---------------")

    async def setup(self):
        """Sets up all initial behaviours for the TruckAgent upon startup."""
        self.add_behaviour(self.ReceiveCFPBehaviour())
        self.add_behaviour(self.ReceiveAcceptanceBehaviour())
        self.add_behaviour(self.ExploreEnvironmentBehaviour())
        self.add_behaviour(self.ReceiveClaimBehaviour())
        self.add_behaviour(self.ReceiveReleaseBehaviour())
        self.add_behaviour(self.ReceiveDeclineClaimBehaviour())
        self.add_behaviour(self.CheckStatusBehaviour())
        self.add_behaviour(self.MoveToBehaviour())
        self.add_behaviour(self.ReceiveAllocatationBehaviour())
        self.add_behaviour(self.Help())
        print(f"[{self.name}] [{self.truck_type}] Truck agent {str(self.jid)} has initialized.")