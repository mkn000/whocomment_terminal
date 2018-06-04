#!/usr/bin/env python3

import sys
import time
import queue
import curses
import logging
import requests
import threading
import browser_cookie3
from re import findall
from collections import deque

log_filename="./whokome_log.out"
logging.basicConfig(filename=log_filename,level=logging.DEBUG)
logging.debug("To log file")

class Whokome():

    def __init__(self,args=[]):
        self.curseInit()
        self.windowsInit()
        self.msg = "<press ENTER to enter comment mode>"
        self.status = ''
        self.viewers = ''
        self.writing = False
        self.resized = False
        self.backlog = deque([])
        self.promptInfo(args)
        self.session = requests.Session()
        self.queue = queue.Queue()
        self.beginViewer()

    def sendComment(self):
        """
        Send comment
        """
        headers = {'Host':'api.whowatch.tv',\
                   'User-Agent':('Mozilla/5.0 (Windows NT 10.0;Win64;x64) '
                                 'AppleWebKit/537.36 (KHTML, like Gecko) '
                                 'Chrome/42.0.2311.135 '
                                 'Safari/537.36 Edge/12.246'),\
                   'Accept':'application/json, text/plain, */*',\
                   'Accept-Language':'en-GB,en;q=0,5',\
                   'Accept-Encoding':'gzip, deflate, br',\
                   'Referer':('https://whowatch.tv/viewer/'+
                              findall('\d+',self.url)[0]),\
                   'Content-Type':('application/x-www-form-urlencoded;'
                                   'charset=utf-8'),\
                   'Content-Length':'0',\
                   'Origin':'https://whowatch.tv',\
                   'DNT':'1',\
                   'Connection':'keep-alive'}
        sending = {'last_updated_at':'%d'%(time.time()*1000),\
                   'message':self.msg}
        self.session.post(self.url+'/comments',data=sending,headers=headers)
        self.msg = "<press ENTER to enter comment mode>"
        self.komepad.clear()
        
    def drawInfo(self):
        """
        Paint comments and status info to terminal
        """
        try:
            while self.status == 'PUBLISHING' or not self.queue.Empty():
                timeinfo = '%01d:%02d / %01d:%02d'%\
                           (*divmod(self.current_time,60),\
                            *divmod(self.time_limit,60))
                self.pos={"title":7,"caster":13,
                          "time_val":self.scrx-len(timeinfo),
                          "viewers_str":self.sxrx-7,
                          "viewers_val":self.scrx-8-len(self.viewers)}
                self.pad.addstr(0,0,"broadcaster:")
                self.pad.addstr(1,0,"title:")
                self.pad.addstr(1,self.pos["viewers_str"],"viewers")
                self.pad.addstr(1,self.pos["viewers_val"],self.viewers)
                self.pad.addstr(0,self.pos["caster"],self.caster)
                self.pad.addstr(1,self.pos["title"],self.title)
                self.pad.addstr(0,self.pos["time_val"],timeinfo)
                if self.time_limit - self.current_time < 300:
                    #red if less than 5 minutes remain
                    self.pad.chgat(0,self.pos["time_val"],6,\
                                   curses.color_pair(4))
                if self.writing == False:
                    self.pad.refresh(0,0,0,0,2,self.winx-1)
                    self.pad.refresh(self.curpos,0,3,0,self.scry-5,self.scrx-1)
                if self.resized:
                    for entry in self.backlog:
                        exec(entry)
                    self.resized = False
                else:
                    try:
                        for i in range(0,4):
                            item = self.queue.get_nowait()
                            #comments
                            for entry in item:
                                printmsg = ('self.pad.addstr(self.winy-1,0,"'+str(entry["who"])+'")',\
                                        'self.pad.chgat(self.winy-1,0,8,'\
                                        'curses.color_pair(3))',\
                                        'self.pad.chgat(self.winy-1,9,1,'\
                                        'curses.color_pair(2))',\
                                        'self.pad.chgat(self.winy-1,11,-1,'\
                                        'curses.color_pair(1))',\
                                        'self.pad.scroll(1)',
                                        'self.pad.addstr(self.winy-1,0,"'+str(entry["msg"])+'")',\
                                        'self.pad.scroll(1)')
                                exec_msg = '%s;%s;%s;%s;%s;%s;%s'%printmsg
                                self.backlog.append(exec_msg)
                                #check duplicate comment
                                if exec_msg != self.backlog[:-1]:
                                    exec(exec_msg)
                                    self.backlog.append(exec_msg)
                                
                                if len(self.backlog) > 100:
                                    self.backlog.popleft()
                    except queue.Empty:
                        pass    
                time.sleep(1)
                self.current_time += 1
        except AttributeError:
            self.scr.clear()
            self.scr.addstr(0,0,'Exiting...')
            self.scr.refresh()

    def updateInfo(self):
        """
        Get updates of comments and other info
        """
        r = self.session.get(self.url)
        try:
            self.status = r.json()["live"]["live_status"]
            self.time_limit = r.json()["live"]["time_limit"]
            self.current_time = r.json()["live"]["running_time"]
            self.caster = r.json()["live"]["user"]["name"]
            self.title = r.json()["live"]["title"]
            while self.status == "PUBLISHING":
                self.status = r.json()["live"]["live_status"]
                comments = []
                kome_ordered = sorted(r.json()["comments"],\
                                      key=lambda comment: comment["posted_at"])
                for kome in kome_ordered:
                    posted = int(str(kome["posted_at"])[:-3])
                    postedStr = time.strftime('%H:%M:%S-!-',\
                                              time.localtime(posted))
                    who = kome["user"]["name"]
                    comment = {'who':'%s%s'%(postedStr,who),\
                               'msg':kome["message"]}
                    comments.append(comment)
                self.queue.put(comments)
                self.viewers = str(r.json()["live"]["view_count"])
                if r.json()["live"]["time_limit"] > self.time_limit:
                    self.time_limit = r.json()["live"]["time_limit"]
                
                time.sleep(0.5)
                try:
                    r = self.session.get(self.url+'?last_updated_at='+\
                                         '%d'%((time.time()-0.5)*1000),timeout=1)
                except requests.exceptions.Timeout:
                    pass
        except KeyError:
            self.status = "invalid_id"

    def beginViewer(self):
        cj = browser_cookie3.load('.whowatch.tv')
        if ".whowatch.tv" in cj._cookies:
            self.cookies_loaded = True
            self.session.cookies = cj
        else:
            self.cookies_loaded = False
        self.pUpdate = threading.Thread(target=self.updateInfo,daemon=True)
        self.pDraw = threading.Thread(target=self.drawInfo)
        self.pUpdate.start()
        time.sleep(3)
        self.pDraw.start()
        lock = threading.Lock()
        try:
        #user inputs handled here
            while self.status == 'PUBLISHING':
                
                self.komepad.addstr(0,0,('comment ('+
                                         str(len(self.msg))+'/100):'))
                self.komepad.addstr(1,0,self.msg)
                self.komepad.refresh(1-self.writing,0,self.scry-3,0,\
                                     self.scry-1,self.scrx-1)
                
                c = self.scr.get_wch(self.scry-2,0)
                if c == curses.KEY_UP and self.curpos > 3:
                    #scroll comment window up for past comments
                    self.curpos -= 1
                    self.pad.refresh(self.curpos,0,3,0,self.scry-5,self.scrx-1)
                elif c == curses.KEY_DOWN:
                    #scroll comment window down
                    if self.curpos < self.winy-18:
                        self.curpos += 1
                        self.pad.refresh(self.curpos,0,3,0,self.scry-5,\
                                         self.scrx-1)
                elif c == '\n':
                    #enter input mode & send comment
                    if self.writing == False:
                        self.writing = True
                        self.msg = ''
                        self.komepad.move(1,0)
                        self.komepad.clrtobot()
                    elif len(self.msg) > 0:
                        self.sendComment()
                        self.writing = False
                elif c == curses.KEY_BACKSPACE:
                    self.msg = self.msg[:-1]
                    self.komepad.clear()
                elif c == curses.KEY_RESIZE:
                    #check terminal resize event
                    curses.update_lines_cols()
                    self.windowsInit()
                    self.resized = True
                elif len(self.msg) < 100 and self.writing:
                    self.msg += c
                    
        except:
            self.status = "user_stop"
        finally:
            time.sleep(1)
            self.close()
            
    def close(self):
        self.pDraw.join()
        self.pUpdate.join()
        curses.nocbreak()
        curses.echo()
        self.scr.keypad(False)
        curses.endwin()
        sys.exit(0)

    def promptInfo(self,args):
        """
        Ask user for url or whowatch live id
        """
        if len(args) == 1:
            openMsg = 'Give live id/ url (quit to exit):'
            self.pad.addstr(0,0,openMsg)
            self.pad.refresh(0,0,0,0,1,self.scrx-1)
            self.scr.refresh()
            given = self.scr.getstr(0,len(openMsg)+1).decode()
        else:
            given = args[1]
        self.pad.erase()    
        if given.isdigit():
            liveId = given
        elif given == "quit":
            self.close()
        elif "whowatch.tv/viewer" not in given:
            self.pad.addstr(0,0,'Invalid url! Exiting...')
            self.pad.refresh(0,0,0,0,1,self.scrx-1)
            self.scr.refresh()
            time.sleep(2)
            self.close()
        else:
            try:
                liveId = findall('d\+',given)[0]
            except IndexError:
                self.pad.addstr(0,0,'Invalid url! Exiting...')
                self.pad.refresh(0,0,0,0,1,self.scrx-1)
                self.scr.refresh()
                time.sleep(2)
                self.close()
        self.url = '%s%s'%('https://api.whowatch.tv/lives/',liveId)

    def windowsInit(self):
        """
        Initialize windows
        """
        self.scrx,self.scry = curses.COLS,curses.LINES
        self.winy = 4*self.scry
        self.winx = self.scrx
        self.curpos = self.winy-(self.scry-7)
        self.pad = curses.newpad(self.winy,self.scrx)
        self.komepad = curses.newpad(4,self.scrx)
        self.pad.idlok(True)
        self.pad.scrollok(True)
        self.pad.setscrreg(3,self.winy-1)
        self.komepad.scrollok(True)
        self.komepad.setscrreg(1,3)
        self.pad.leaveok(False)
        self.komepad.leaveok(False)

    def curseInit(self):
        """
        Initialize curses
        """
        self.scr = curses.initscr()
        self.scr.keypad(True)
        self.scr.leaveok(False)
        curses.noecho()
        curses.curs_set(0)
        curses.start_color()
        curses.use_default_colors()
        curses.init_pair(1,curses.COLOR_CYAN,-1) #cyan on def. background
        curses.init_pair(2,curses.COLOR_BLUE,-1) #blue 
        curses.init_pair(3,curses.COLOR_GREEN,-1) #green
        curses.init_pair(4,curses.COLOR_RED,-1) #red
        self.scr.refresh()

    def __del__(self):
        self.scr.keypad(False)
        curses.endwin()

if __name__=='__main__':
    try:
        viewer = Whokome(sys.argv)
    except:
        logging.exception("Exception")
        raise
