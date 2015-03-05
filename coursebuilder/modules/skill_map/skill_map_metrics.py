# Copyright 2015 Google Inc. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS-IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Module to calculate metrics for the SkillMap object."""

__author__ = 'Milagro Teruel (milit@google.com)'


import networkx
from collections import defaultdict

CHAINS_MIN_LENGTH = 10  # TODO(milit) Add this as a setting?


class SkillMapMetrics(object):
    """This class works as interface with networkx library.

    Holds a DiGraph equivalent to the skill map, created at initialization.
    """

    def __init__(self, skill_map):
        """Creates an instance of networkx.DiGraph from a skill_map object."""
        self.nxgraph = networkx.DiGraph()
        self.successors = skill_map.build_successors()
        for node, dsts in self.successors.iteritems():
            for dst in dsts:
                self.nxgraph.add_edge(node, dst)
            if not dsts:  # Add the single node
                self.nxgraph.add_node(node)

    def simple_cycles(self):
        """Finds the simple cycles (with no repeated edges) in the graph.

        A cycle is called simple if no node is repeated.

        Returns:
            A list with cycles. Each cycle is represented as a list of
            skills ids in the order they appear in the graph.
        """
        return list(networkx.simple_cycles(self.nxgraph))

    def singletons(self):
        """A singleton is a weakly connected component that has only one node.

        Returns:
            A list with the singleton nodes.
        """
        components = networkx.weakly_connected_components(self.nxgraph)
        return [component[0] for component in components
                if len(component) == 1]

    def _get_longest_paths(self, src, destinations, min_length, topo_sort):
        """Returns the paths from src to destinations longer than min_length.

        See also: http://en.wikipedia.org/wiki/Longest_path_problem, section
        "Acyclic graphs and critical paths". This implementation is in
        reverse order with respect to the algoritm in the article.

        Args:
            src: a node of the graph. It is the start of the paths returned.
            destinations: an iterable of nodes in the graph. Only one path
            (if any) in the returned set will end in each of this nodes.
            min_len: a number. Minimum size of the path to be returned by
            this method.
            topo_sort: a sorted iterable of the nodes in the graph. The order
            corresponds to one of the topological orders of the graph.

        Returns:
            A list of paths starting at src and ending at one of the nodes in
            destinations. Each path is represented as a sorted list of
            nodes, and has a length smaller than min_length.
        """
        def get_path_from_ancestors(ancestors, dst):
            """Traverses the ancestors dict to find the path ending at dst.

            Args:
                ancestors: a dictionary. Represents a path in the graph that
                ends at destination. Maps nodes to their ancestor in this path.
                dst: the node ending the path.

            Returns:
                A path ending at dst represented as an ordered list of nodes.
            """
            current_dst = ancestors[dst]
            path = [dst]
            while current_dst:
                path.insert(0, current_dst)  # insert at the begginning
                current_dst = ancestors[current_dst]
            return path

        # Contruct the distances and ancestors from src to all nodes in nxgraph.
        # Maps nodes to its ancestors in longest path.
        ancestors = {src: None}
        # Maps nodes to distance from src in longest path.
        distances = defaultdict(lambda: -1)  # -1 means not reachable.
        distances[src] = 0
        for next_dst in topo_sort:
            if distances[next_dst] == -1:  # No visited -> no connected to src.
                continue
            for successor in self.successors[next_dst]:
                if distances[successor] < distances[next_dst] + 1:
                    ancestors[successor] = next_dst
                    distances[successor] = distances[next_dst] + 1

        # Construct the paths only to the nodes in destinations
        result = []
        for dst in destinations:
            if distances[dst] >= min_length:
                result.append(get_path_from_ancestors(ancestors, dst))
        return result

    def long_chains(self, min_length=None):
        """Finds non cyclic shortest paths longer or equal that min_length.

        The graph must be ACYCLIC. The complexity of the algorithm is:
            O(topo_sort) + O(|edges|*|nodes|*|nodes with no ancestors|)
            = O(|edges|*|nodes|*|nodes with no ancestors|)
        No simple path in the result is contained inside other simple path.

        Args:
            min_length: The minimum length of a chain to be returned by the
            function. If min_length is None, the maximum length for the path is
            modules.skill_map.skill_map_metrics.CHAINS_MIN_LENGTH. The length
            of a chain is the numbers of edges in the chain.

        Returns:
            A list of long chains. Each long chain is an ordered list of
            nodes that forms the path.

        Raises:
            networkx.NetworkXUnbounded if the graph has a cycle.
        """

        if not min_length:
            min_length = CHAINS_MIN_LENGTH

        # We can do this from the nxgraph, but this has better complexity.
        if not self.successors:
            return []
        initial_nodes = set(
            self.successors.keys()) - reduce(
            set.union, self.successors.values())  # nodes with no ancestors
        # nodes with no successors
        end_nodes = [node for node in self.successors
                     if not self.successors[node]]

        result = []
        topo_sort = networkx.topological_sort(self.nxgraph)
        for src in initial_nodes:
            result.extend(self._get_longest_paths(
                src, end_nodes, min_length, topo_sort))
        return result

    def diagnose(self):
        """Calculates information about the health of the graph.

        Returns:
            A dictionary with the following structure:
                {
                    'cycles': [[ids of skills forming cycle], [...], ...],
                    'singletons': [skill_ids],
                    'long_chains': [[skill_ids...], [...], ...],
                }
            The minimum length that a chain must have to be included into the
            long_chains field is
            modules.skill_map.skill_map_metrics.CHAINS_MIN_LENGTH. If any
            cycle is found in the graph, there will be no calculation of long
            chains.
        """
        cycles = self.simple_cycles()
        long_chains = []
        if not cycles:
            long_chains = self.long_chains()
        return {
            'cycles': cycles,
            'singletons': self.singletons(),
            'long_chains': long_chains
        }
