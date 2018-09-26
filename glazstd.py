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

class GlazStd(Peer):
    def post_init(self):
        print "post_init(): %s here!" % self.id
        self.state = dict()
    
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
        S = 4   # total unchoke slots
        round = history.current_round()
        logging.debug("%s again.  It's round %d." % (
            self.id, round))
        if round != 0:
            last_round_dl = history.downloads[round-1]
            second_last_round_dl =history.downloads[round-2]
        # One could look at other stuff in the history too here.
        # For example, history.downloads[round-1] (if round != 0, of course)
        # has a list of Download objects for each Download to this peer in
        # the previous round.
        chosen = []

        if len(requests) == 0:
            logging.debug("No one wants my pieces!")
            bws = []
        else:
            # pick S-1 most cooperative peers with requests to unchoke
            downloads_per_peer = {peer.id:0 for peer in peers}
            for dl in last_round_dl:
                downloads_per_peer[dl.from_id] += dl.blocks
            for dl in second_last_round_dl:
                downloads_per_peer[dl.from_id] += dl.blocks
            cooperative_peers = sorted(downloads_per_peer, key=lambda x:x[1])

            requester_ids = set([r.requester_id for r in requests])
            i = 0
            # print("COOPERATIVE PEERS:", cooperative_peers)
            # print("REQUESTER IDS:", requester_ids)
            for p in cooperative_peers:
                if p in requester_ids:
                    chosen.append(p)
                if len(chosen) == S-1:
                    break;
            # print("CHOSEN:", chosen)
            # optimistically unchoke 1 every 3 rounds
            if round % 3 == 0 or "optimistic_id" not in self.state:
                optimistic_id = random.choice(tuple(set(cooperative_peers) - set(chosen)))
                self.state["optimistic_id"] = optimistic_id
            else:
                optimistic_id = self.state["optimistic_id"]
            chosen.append(optimistic_id)

            # Evenly "split" my upload bandwidth among the one chosen requester
            bws = even_split(self.up_bw, len(chosen))

        # create actual uploads out of the list of peer ids and bandwidths
        uploads = [Upload(self.id, peer_id, bw)
                   for (peer_id, bw) in zip(chosen, bws)]
            
        return uploads
