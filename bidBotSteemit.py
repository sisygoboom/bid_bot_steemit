# -*- coding: utf-8 -*-
"""
Created on Sun Feb 25 08:25:07 2018

@author: chris
"""

from steem import Steem
from steem.blockchain import Blockchain
from steem.steemd import Steemd
from steem.converter import Converter
from steem.instance import set_shared_steemd_instance
from steem.account import Account
from steem.post import Post
from time import sleep
import time
import datetime
from threading import Thread
from coinmarketcap import Market
from steemdata import SteemData
import json
import socket
from pathlib import Path

class earnings:
    ### Called upon startup, this creates the earnings file if there isn't already one
    def __init__(self):
        self.daily_sbd = 0.0
        self.daily_steem = 0.0
        if Path("earnings.txt").is_file():
            i = open("earnings.txt","r").readlines()
            self.daily_sbd = float(i[0])
            self.daily_steem = float(i[1])
        self.writeToFile()
        
    ### Save steem/sbd earnings to earnings.txt
    def writeToFile(self):
        earnings = open("earnings.txt", "w")
        earnings.write("%s\n%s" % (str(self.daily_sbd),str(self.daily_steem)))
        earnings.close()
        print(self.daily_sbd)
        print(self.daily_steem)
        print("written")
    
    ### Adds new bids to the earnings
    def add(self, qty, asset):
        if asset == 'STEEM':
            self.daily_steem += qty
        elif asset == 'SBD':
            self.daily_sbd += qty
        self.writeToFile()
    
    ### Called at payout, returns a dictionary with steem/sbd earnings and resets the two to 0
    def flush(self):
        total_daily_earnings = {'STEEM':self.daily_steem,'SBD':self.daily_sbd}
        self.daily_sbd = 0.0
        self.daily_steem = 0.0
        self.writeToFile()
        print('flushed')
        return total_daily_earnings
    
    ### This is the main loop, it executes every 2.4 hours from startup time
    def counter(self):
        track = 0
        # The start time is used for optimal accuracy
        starttime = time.time()
        while True:
            # This is much better than sleep(8640), it means time spent calculating does not push back the vote
            to_wait = 8640 - ((time.time() - starttime) % 8640)
            sleep(to_wait)
            # push 'current round' data to 'previous round' data
            bidding_data = bidM.dequeue()
            # Distribute the votes between bidders
            sweep(bidding_data)
            
            # this is used to work out when 24 hours is up for payouts to delegators
            track += 1
            if track == 10:
                track = 0
                payout()

class bidManage:
    ### called at startup, loads/creates bidding data dictionary for the data file for the steem bot tracker API
    def __init__(self):
        if Path(dirLoc+"data").is_file():
            with open(dirLoc+'data', 'r') as data:
                data = data.read()
                self.bidding_data = json.loads(data)
        else: self.bidding_data = {"current_round": [], "last_round": []}
        self.save()
    
    ### Pushes 'current round' to 'last_round'
    def dequeue(self):
        self.bidding_data['last_round'] = self.bidding_data['current_round']
        self.bidding_data['current_round'] = []
        self.save()
        return self.bidding_data['last_round']
    
    ### Save the bidding data to 'data', called whenever a change is made
    def save(self):
        with open(dirLoc+'data', 'w') as data:
            data.write(json.dumps(dict(self.bidding_data)))
            print(self.bidding_data)
    
    ### Add a new bid to 'current_round'
    def enqueue(self, dataset):
        self.bidding_data['current_round'].append(dataset)
        self.save()
    
    ### This is the mainloop for bidManage
    ### It streams transactions on the blockchain
    def stream(self):
        global nodes
        lost_connection = 0
        lost_connection_td = datetime.datetime.now()
        #last_block = b.get_current_block_num()
        retry_count = 0
        failover_count = 0
        while True:
            try:
                retry_count = 0
                failover_count = 0
                for i in b.stream(filter_by=['transfer']):
                    # if bot was down, connection has resumed
                    if upordown.up == False:
                        # Update JSON metadata to let steem bot tracker know bot is back online
                        upordown.setJSONMeta(True)
                        # record downtime in minutes and time when we got back online
                        now = datetime.datetime.now()
                        diff = time.time() - lost_connection
                        timeout_string = str(diff/60) + " from " + lost_connection_td + " until " + str(now)
                        print("out for " + timeout_string)
                        with open("downtime.log","a+") as logfile:
                            logfile.write(timeout_string)
                        
                    # If bid is to the bot
                    if i['to'] == acc_name:
                        # verify the transaction
                        refund = verifyTransaction(i)
                        
                        # if a string is returned, a refund is due
                        if type(refund) == str:
                            # payed[0] is either 'SBD'/'STEEM', payed[1] is username
                            payed = i['amount'].split(' ')
                            # commit to refund
                            s.commit.transfer(i['from'],
                                      float(payed[0]),
                                      payed[1],
                                      memo="Sorry, we couldn't upvote the post '" + i['memo'] + refund,
                                      account=acc_name)
                            
                        # if a dictionary is returned, we have a valid bid
                        if type(refund) == dict:
                            #add the bid to earnings and the bidding data
                            print(refund['amount'])
                            earn.add(refund['amount'],refund['currency'])
                            self.enqueue(refund)
                            
            except Exception as e:
                print(e)
                print(" Exception 1")
                
                if upordown.up == True:
                    # Updates the bots JSON metadata so steem bot tracker knows it is offline
                    upordown.setJSONMeta(False)
                    # record start of downtime
                    lost_connection = time.time()
                    lost_connection_td = datetime.datetime.now()
                
                if failover_count < len(nodes):
                    nodes = nodes[1:] + nodes[:1]
                    failover_count += 1
                    continue
                
                retry_count += 1
                if retry_count == 2:
                    retry_count = 0
                    nodes = nodes[1:] + nodes[:1]
                    # This will only happen when connection to the stream is lost
                        
                #prevent ddos'ing
                sleep(180)

### verify a transaction to make sure it can be bid on, called whenever a new
### bid is recieved.
def verifyTransaction(transaction):
    # Make sure transaction is incoming
    if not transaction['from'] == acc_name:
        # get all transaction information
        memo = transaction['memo']
        bidder = transaction['from']
        bid = transaction['amount']
        # bid[0] will be either 'SBD'/'STEEM'
        # bid[1] will be the quantity
        bid = bid.split(' ')
        bid[0] = float(bid[0])
        
        # Loads the blacklist and returns False if a match is found meaning no refund
        # Bots such as minnowbooster that also offer auto-refunds should be blacklisted
        # This is to stop a refund loop
        blacklist = open('blacklist.txt','r').read().split("\n")
        if bidder in blacklist:
            return False
        
        # If bid is below minimum bid, refund the customer
        if bid[0] < min_bid:
            return "'. Please send a minimum of " + str(min_bid) + " SBD/STEEM."
        
        # Make sure URL is for steemit or busy as they share the same url format
        if memo.startswith('https://steemit.com/') or memo.startswith('https://busy.org/'):
            memo = memo.replace('https://steemit.com/','')
            
            # work out if url is to a comment
            memo = memo.split('#')
            comment_post = memo[0]
            if len(memo) == 2:
                if memo[1].startswith("@") == True:
                    comment_post = memo[1]
            
            # break url into username and permlink
            url = comment_post.replace('@','')
            url = url.split('/')
            
            # remove the tag from url
            if len(url) == 3:
                del url[0]
                
            # if post has already been bid on this round provide a refund
            for i in bidM.bidding_data['current_round']:
                if i['url'] == url:
                    return "'. The URL you have supplied has already been bid on this round."
                
            # make sure the bot hasn't already voted on the post
            active_votes = s.get_active_votes(url[0], url[1])
            if not any(d['voter'] == acc_name for d in active_votes):
                # attempt to get post age in days
                try:
                    age = Post('@' + url[0] + '/' + url[1]).time_elapsed()
                    # if post is older than 4 days, add the bid to the database
                    if age.days <= max_age and age.seconds/60 >= min_age:
                        transfer = {}
                        transfer['permlink'] = url[1]
                        transfer['author'] = url[0]
                        transfer['sender'] = bidder
                        transfer['amount'] = bid[0]
                        transfer['currency'] = bid[1]
                        transfer['url'] = transaction['memo']
                        return transfer
                    else:
                        # the post is older than 4 days meaning it is likely reward abuse, provide refund
                        return "'. The post must not be older than " + max_age + " days or younger than " + min_age + " minutes - we do this in the interests of abuse prevention."
                except Exception as e:
                    # the url is not valid as a post object could not be made, provide refund
                    return "'. An error occured while trying to access the post - check to make sure all spelling is correct and there is no unexpected spaces."
            else:
                # post has already been voted on, provide refund
                return "'. We have  already voted on this post - in the interests of saving you money we've refunded you."
        else:
            # not a steemit or busy url, refund
            return "'. Please send a https://steemit.com/ or https://busy.org/ URL."
    return False

### payout module called every 24 hours
def payout():
    # steemdata is used to work out who the delegators are
    sd = SteemData()
    # get the daily earnings
    balance_sheet = earn.flush()
    print(balance_sheet)
    # get the payout blacklist, this is for accounts you don't want to earn from your service
    # also used to prevent paying out to paid SP rentals
    exclusions = open("exclusions.txt","r").read().split("\n")
    
    # gets a list of all delegators and vesting shares they've delegated
    delegations = sd.Operations.find( {
    '$and': [
        {'type' : 'delegate_vesting_shares'},
        {'delegatee': acc_name}
    ]
} )  
    delegation_map = dict()
    total = 0
    
    # create an easy to use dictionary with all eligible delegators and vesting shares
    for delegation in delegations:
        delegator = str(delegation['delegator'])
        vestings = delegation['vesting_shares']
        amount = vestings['amount']
        total += float(amount)
        # blacklist filter
        if delegator not in exclusions:
            delegation_map[delegator] = amount
        
    # Pay out loop
    for delegator in sorted(delegation_map):
        # won't pay out if delegation is below specified SP
        if c.vests_to_sp(delegation_map[delegator]) > min_delegation:
            # calculate what percent of the daily earnings the delegator is entitled to
            ratio = (delegation_map[delegator]/total)*payout_percent
            # delegators earn both steem and SBD
            steem_earnings = round(balance_sheet['STEEM']*ratio,3)
            sbd_earnings = round(balance_sheet['SBD']*ratio,3)
            
            # if earnings are larger than 0, pay out
            if steem_earnings > 0:
                s.commit.transfer(delegator,
                                  steem_earnings,
                                  'STEEM',
                                  memo=("Here's your STEEM earnings for the day boss! " + 
                                        str(round(ratio*100,4)) + "% of " + 
                                        str(balance_sheet['STEEM'])),
                                  account=acc_name)
            # don't want to ddos them
            sleep(25)
            #if earnings larger than 0, pay out
            if sbd_earnings > 0:
                s.commit.transfer(delegator,
                                  sbd_earnings,
                                  'SBD',
                                  memo=("Here's your SBD earnings for the day boss! " + 
                                        str(round(ratio*100,4)) + "% of " + 
                                        str(balance_sheet['SBD'])),
                                  account=acc_name)
                
### Distribute the vote between bidders, called every 2.4 hours
def sweep(all_votes):
    # Get steem/sbd prices
    cmc = Market()
    steem_mc = float(cmc.ticker('STEEM', convert='USD')[0]['price_usd'])
    sbd_mc = float(cmc.ticker('steem-dollars', convert='USD')[0]['price_usd'])
    
    # Calculates the total value of all votes
    totalVal = 0.0
    for bid_item in all_votes:
        quant = bid_item['amount']
        # if bid in sbd, multiply quantity by sbd market cap and make dictionary entry
        if bid_item['currency'] == 'SBD':
            bid_item['usd'] = sbd_mc*quant
        # if bid in steem, multiply quantity by steem market cap and make dictionary entry
        if bid_item['currency'] == 'STEEM':
            bid_item['usd'] = steem_mc*quant
        # add to total
        totalVal += bid_item['usd']
        
    # Vote on posts
    for data in all_votes:
        # calculate weight by deviding bid by total bids value
        weight = (data['usd']/totalVal)*100
        #make a post object to operate on
        subject = Post('@' + data['author'] + '/' + data['permlink'])
        
        # vote on post
        try: subject.vote(weight, voter=acc_name)
        except Exception as e:
            print(e)
            print(" Exception2")
        
        #leave a comment on the post
        try: subject.reply("You recieved a " + str(round(weight,3)) + 
                           "% upvote from @" + data['sender'] + "!",
                           "", acc_name)
        except Exception as e:
            print(e)
            print(" Exception 3")
        #any faster than 20s and you'd be ddos'ing the server
        sleep(22)
        
##############################################################
### This is all customiseable data and depends on your bot ###
##############################################################
### This procedure changes the account JSON data to let users know whether it
### is on or off. Pass True for on and False for off.
class acc:
    def __init__(self):
        self.up = True
    def setJSONMeta(self, on):
        if on == True:
            s.commit.update_account_profile(
            {"profile":
                {"cover_image":"https://i.imgur.com/UoAuSO2.png",
                 "profile_image":"https://i.imgur.com/FE2IyHE.png",
                 "name":"Steem Roasted",
                 "about":"Bidbot. Send STEEM or SBD with a link to the post and \
                 we'll upvote the post! Minimum bid is " + str(min_bid) + 
                 ". Automatic refunds. 100% payouts to delegators.",
                 "location":"Undisclosed",
                 "website":"https://discord.gg/MHzUVN"},
                 "config":
                     {"min_bid_sbd":min_bid,
                      "min_bid_steem":min_bid,
                      "bid_window":2.4,
                      "comments":"true",
                      "posts_comment":"true",
                      "refunds":"true",
                      "accepts_steem":"true",
                      "funding_url":"",
                      "tags":"",
                      "api_url":"",
                      "max_post_age":max_age,
                      "min_post_age":min_age,
                      "is_disabled":"false"}},
                    acc_name)
        if on == False:
            s.commit.update_account_profile(
            {"profile":
                {"cover_image":"https://i.imgur.com/UoAuSO2.png",
                 "profile_image":"https://i.imgur.com/FE2IyHE.png",
                 "name":"Steem Roasted Is Down",
                 "about":"Any funds sent might not be bidded on in the next \
                 immediate round but bids are still being accepted.",
                 "location":"Undisclosed",
                 "website":"https://discord.gg/MHzUVN"},
                 "config":
                     {"min_bid_sbd":min_bid,
                      "min_bid_steem":min_bid,
                      "bid_window":2.4,
                      "comments":"true",
                      "posts_comment":"true",
                      "refunds":"true",
                      "accepts_steem":"true",
                      "funding_url":"",
                      "tags":"",
                      "api_url":"",
                      "max_post_age":max_age,
                      "min_post_age":min_age,
                      "is_disabled":"false"}},
                    acc_name)
        self.up = on
    

keys = ['PRIVATE_POSTING_KEY',
        'PRIVATE_ACTIVE_KEY']

nodes = ['https://rpc.buildteam.io',
         'https://api.steemit.com',
         'https://steemd.steemitstage.com/',
         'https://gtg.steem.house:8090',
         'https://steemd.steemgigs.org']

dirLoc = 'C:\\your\\hosting\\directory'

# Initialise the classes
set_shared_steemd_instance(Steemd(nodes=nodes))
s = Steem(nodes, keys=keys)
b = Blockchain()
c = Converter()
earn = earnings()
bidM = bidManage()
upordown = acc()

acc_name = 'ACCOUNT_NAME'
min_bid = 0.05
payout_percent = 1 #1=100%, 0.5=50%
min_delegation = 20
max_age = 4 #days
min_age = 0 #minutes
acc = Account(acc_name)

# This only really works if you're hosting the data file on your own PC, I was
# using WAMP server for windows but my ISP wouldn't allow a static IP
ip = socket.gethostbyname(socket.gethostname())
api = "https://" + ip + "/data"

##############################################################
### This is all customiseable data and depends on your bot ###
##############################################################

# update account metadata to let steem bot tracker know the bot is online
upordown.setJSONMeta(True)
    
# Start the main loops
countloop = Thread(target=earn.counter)
countloop.start()
bidM.stream()