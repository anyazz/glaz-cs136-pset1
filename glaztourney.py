#!/usr/bin/python

# This is a dummy peer that just illustrates the available information your peers
# have available.

# You'll want to copy this file to AgentNameXXX.py for various versions of XXX,
# probably get rid of the silly logging messages, and then add more logic.

import random
import logging
from math import floor

from messages import Upload, Request
from util import even_split
from peer import Peer

class GlazTourney(Peer):
    def post_init(self):
        print "post_init(): %s here!" % self.id
        self.dummy_state = dict()
        self.dummy_state["cake"] = "lie"

    def requests(self, peers, history):
        """
        peers: available info about the peers (who has what pieces)
        history: what's happened so far as far as this peer can see

        returns: a list of Request() objects

        This will be called after update_pieces() with the most recent state.
        """
        needed = lambda i: self.pieces[i] < self.conf.blocks_per_piece

        # list of integers representing ids of pieces needed
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
        if self.pieces:
            for (piece_id, _) in piece_frequency_items:
                start_block = self.pieces[piece_id]
                for owner in piece_ownerid[piece_id]:
                    r = Request(self.id, owner, piece_id, start_block)
                    requests.append(r)
        else:
            start_block = self.pieces[0]
            for owner in piece_ownerid[0]:
                if owner[:4] == 'seed':
                    r = Request(self.id, owner, 0, start_block)
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

        round = history.current_round()

        # look at past round to determine previously cooperative peers
        if round >= 1:
            last_round_dl = history.downloads[round-1]

        # initialize array of chosen peers to unchoke and bandwidths to give
        chosen = []
        bws = []

        # check if no peers need to be unchoked
        if len(requests) != 0:
            # Step 1: Calculate bandwidth for all requesters that have uploaded to us

            # count total downloaded blocks from each peer in last round
            downloads_per_peer = {peer.from_id:peer.blocks for peer in last_round_dl}

            # calculate total blocks downloaded from requesters
            total_blocks = 0
            for blocks in downloads_per_peer.values():
                total_blocks += blocks

            # determine requesters not downloaded from last round
            reqs = set([req.requester_id for req in requests])
            downloaded_reqs = set(downloads_per_peer.keys())
            remaining = reqs - downloaded_reqs

            # allocate 10% for optimistic unchoking if there are requesters who
            # did not upload last round
            if remaining:
                # unchoke each peer and calculate bandwidth
                for peer, blocks in downloads_per_peer.items():
                    chosen.append(peer)
                    bws.append(floor(blocks * 0.9 / total_blocks))

                # Step 2: optimistically unchoke 1 peer not downloaded from
                bws.append(self.up_bw - sum(bws))
                chosen.append(random.choice(list(remaining)))
            # if all requesters uploaded last round, allocate 100% accordingly
            else:
                # unchoke each peer and calculate bandwidth
                for peer, blocks in downloads_per_peer.items():
                    chosen.append(peer)
                    bws.append(floor(blocks / total_blocks))

        # create actual uploads out of the list of peer ids and bandwidths
        uploads = [Upload(self.id, peer_id, bw)
                   for (peer_id, bw) in zip(chosen, bws)]

        return uploads
