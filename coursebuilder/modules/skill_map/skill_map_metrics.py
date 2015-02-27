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


from networkx import DiGraph
from networkx import simple_cycles


class SkillMapMetrics(object):
    """This class works as interface with networkx library.

    Holds a DiGraph equivalent to the skill map, created at initialization.
    """

    def __init__(self, skill_map):
        """Creates an instance of networkx.DiGraph from a skill_map object."""
        self.nxgraph = DiGraph()
        successors = skill_map.build_successors()
        for node, dsts in successors.iteritems():
            for dst in dsts:
                self.nxgraph.add_edge(node, dst)

    def simple_cycles(self):
        """Finds the simple cycles (with no repeated edges) in the graph.

        A cycle is called simple if no node is repeated.

        Returns:
            A list with cycles. Each cycle is represented as a list of
            skills ids in the order they appear in the graph.
        """
        return list(simple_cycles(self.nxgraph))
