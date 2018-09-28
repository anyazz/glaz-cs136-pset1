#!/usr/bin/python

# This is a dummy peer that just illustrates the available information your peers 
# have available.

# You'll want to copy this file to AgentNameXXX.py for various versions of XXX,
# probably get rid of the silly logging messages, and then add more logic.

import random
import logging

from messages import Upload, Request
from util import even_split
from peer import Peer

class GlazTyrant(Peer):
    def post_init(self):
        print "post_init(): %s here!" % self.id
        self.consecutive_unchokes = {}
        self.expected_dl = {}
        self.expected_ul = {}
    
    def requests(self, peers, history):
        """
        peers: available info about the peers (who has what pieces)
        history: what's happened so far as far as this peer can see

        returns: a list of Request() objects

        This will be called after update_pieces() with the most recent state.
        """
        needed = lambda i: self.pieces[i] < self.conf.blocks_per_piece
        needed_pieces = filter(needed, range(len(self.pieces)))
        np_set = set(needed_pieces)

        requests = []   # We'll put all the things we want here
        
        # count frequency of each needed piece among available pieces from peers,
        # keeping track of owners of each needed piece
        piece_frequency = {piece:0 for piece in needed_pieces}
        piece_ownerid = {piece:[] for piece in needed_pieces}
        for peer in peers:

            # get pieces that peer has and we need
            av_set = set(peer.available_pieces)
            isect = av_set.intersection(np_set)

            # iterate through and update frequency and owner of piece
            for piece in isect:
                piece_frequency[piece] += 1;
                piece_ownerid[piece].append(peer.id)

        # get list of needed pieces as (piece_id, frequency) list and randomly shuffle
        # to make sure that not all agents request same pieces with same rarity at the same time
        # (since all start at rarity 2)
        piece_frequency_items = piece_frequency.items()
        random.shuffle(piece_frequency_items)

        # sort list by rarity (increasing frequency)
        piece_frequency_items = sorted(piece_frequency_items, key=lambda x: x[1])

        # iterate through list and request each piece from each of its current owners
        for (piece_id, _) in piece_frequency_items:
            start_block = self.pieces[piece_id]
            for owner in piece_ownerid[piece_id]:
                r = Request(self.id, owner, piece_id, start_block)
                requests.append(r)
        return requests

    def uploads(self, requests, peers, history):
        """
        requests -- a list of the requests for this peer for this round
        peers -- available info about all the peers
        history -- history for all previous rounds

        returns: list of Upload objects.

        In each round, this will be called after requests().
        """
        # intial values
        c = 0.1
        r = 3   #periods
        a = 0.2
        round = history.current_round()

        # randomly shuffle peers to avoid symmetry effects
        random.shuffle(peers)

        # initialize state variables
        if self.consecutive_unchokes == {}:
            self.consecutive_unchokes = {peer.id: 0 for peer in peers}
        if self.expected_dl == {}:
            self.expected_dl = {peer.id: 0 for peer in peers}
        if self.expected_ul == {}:
            self.expected_ul = {peer.id: 1 for peer in peers}
        
        requester_ids = set([r.requester_id for r in requests])
        peer_ids = set([peer.id for peer in peers])

        # count total downloaded blocks from each peer in last round,
        # update expected UL and DL
        if round >= 1:
            unchoker_ids = set([])
            last_dl = history.downloads[round-1]
            second_last_ul = history.uploads[round-2]
            downloads_per_peer = {peer.id:0 for peer in peers}
            unchoked_ids = set([])

            for dl in last_dl:
                downloads_per_peer[dl.from_id] += dl.blocks
                unchoker_ids.add(dl.from_id)
            for ul in second_last_ul:
                unchoked_ids.add(ul.from_id)

            for peer_id in unchoker_ids:
                self.expected_dl[peer_id] = downloads_per_peer[peer_id]
                self.consecutive_unchokes[peer_id] += 1
                if self.consecutive_unchokes >= r:
                    self.expected_ul[peer_id] *= (1 - c)
            
            for peer_id in peer_ids - unchoker_ids:
                self.expected_ul[peer_id] *= (1 + a) 
                self.consecutive_unchokes[peer_id] = 0

        chosen = set([])
        cooperative_peers = sorted(requester_ids, key=lambda x: -float(self.expected_dl[x]) / float(self.expected_ul[x]))
        k, ul_bw, uploads = 0, 0, []
        for peer_id in cooperative_peers:
            temp = ul_bw + self.expected_ul[peer_id]
            if temp > self.up_bw:
                break;
            ul_bw = temp
            chosen.add(peer_id)
            uploads.append(Upload(self.id, peer_id, self.expected_ul[peer_id]))

        unchosen = set(requester_ids) - chosen
        if len(unchosen) == 0:
            unchosen = set(peer_ids) - chosen
        optimistic_id = random.choice(tuple(unchosen))
        uploads.append(Upload(self.id, optimistic_id, (self.up_bw - ul_bw)))

        return uploads

