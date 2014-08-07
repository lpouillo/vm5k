from urlparse import urlparse
from threading import Thread
import httplib, sys
from Queue import Queue
import sys, getopt
import time

writingQueue = Queue()

def doWork():
    while True:
        args_list=q.get()
        
        servlet = args_list[0]
        url = args_list[1]
        client_id = args_list[2]
        
        start_time = time.clock() * 1000
        status,url=getStatus(url)
        end_time = time.clock() * 1000
       
        duration = end_time - start_time
        
        doSomethingWithResult(duration,url,client_id,servlet)
        
        q.task_done()

def getStatus(ourl):
    try:
        url = urlparse(ourl)
        conn = httplib.HTTPConnection(url.netloc)   
        conn.request("GET", url.path)
        res = conn.getresponse()
        return res.status, ourl
    except:
        return "error", ourl

def doSomethingWithResult(duration,url,client_id,servlet):
    writingQueue.put([ duration,url,client_id,servlet ])

def WriteToFile(output_file,scenario,concurrent_req):
    f = open(output_file,'a')
    while not writingQueue.empty():
        args_list=writingQueue.get()
        duration = args_list[0]
        url = args_list[1]
        client_id = args_list[2]
        servlet = args_list[3]
        
        f.write(str(duration)+","+url+","+str(client_id)+","+servlet+","+scenario+","+str(concurrent_req)+"\n")
    f.close()
    
if __name__ == "__main__":
    
    argv = sys.argv[1:]
    
    try:
        opts, args = getopt.getopt(argv,"hi:o:",["ip_address=","ofile="])
    except getopt.GetoptError:
        print 'test.py -i <ip_address> -o <outputfile>'
        sys.exit(2)
    for opt, arg in opts:
        if opt == '-h':
            print 'test.py -i <ip_address> -o <outputfile>'
            sys.exit()
        elif opt in ("-i", "--ip"):
            ip_address = arg
        elif opt in ("-o", "--outputfile"):
            output_file = arg
    
    
    base_url = "/rubbos/servlet/"
    
    servlet_list = ["edu.rice.rubbos.servlets.StoriesOfTheDay",
                    "author.html",
                    "register.html",
                    "edu.rice.rubbos.servlets.Search",
                    "browse.html",
                    "edu.rice.rubbos.servlets.ViewStory",
                    "edu.rice.rubbos.servlets.BrowseCategories"]
    
    client_id = 100000
    
    storyId = 11667
    
    add_extra_url = ["edu.rice.rubbos.servlets.ViewStory"]
    
    q=Queue()
    
    max_concurrent = 128
    
    #print "Launching threads..."
    for i in range(max_concurrent):
        t=Thread(target=doWork)
        t.daemon=True
        t.start()


    #print "Launching scenario #1"    
    for n_thread in range(max_concurrent):
        try:
            for servlet in servlet_list:
                #print "Servlets "+servlet+" max concurrent "+str(n_thread)
                for rep in range(n_thread+1):
                    if servlet in add_extra_url:
                        q.put([ servlet,"http://"+ip_address+base_url+servlet+"?storyId="+str(storyId)+"&clientID="+str(client_id),client_id ])
                    else:
                        q.put([ servlet,"http://"+ip_address+base_url+servlet+"&clientID="+str(client_id),client_id ])
                    client_id+=1
                
                q.join()
                WriteToFile(output_file,"1",str(n_thread))
                
        except KeyboardInterrupt:
            sys.exit(1)
            
            
    storyIds = ["10038", "10461", "10638","10716","10743","10884","11313","11375","11667","4199","7003","8984","9464","9474","9735","9806","9905"]
    servlet = "edu.rice.rubbos.servlets.ViewStory"
    
    #print "Launching scenario #2"
    for n_thread in range(max_concurrent):
        try:
            for storyId in storyIds:
                #print "Servlets "+servlet+" "+str(storyId)
                for rep in range(n_thread+1):
                    q.put([ servlet,"http://"+ip_address+base_url+servlet+"?storyId="+str(storyId)+"&clientID="+str(client_id),client_id ])
                    client_id+=1
                q.join()
                WriteToFile(output_file,"2",str(n_thread))
        except KeyboardInterrupt:
            sys.exit(1)
            
    print "Launching scenario #3"
    for n_thread in range(max_concurrent):
        try:
            for rep in range(n_thread+1):
                #print "Servlets "+servlet+" "+str(rep)
                for storyId in storyIds:
                    q.put([ servlet,"http://"+ip_address+base_url+servlet+"?storyId="+str(storyId)+"&clientID="+str(client_id),client_id ])
                    client_id+=1
                
                q.join()
                
                WriteToFile(output_file,"3",str(n_thread))
        except KeyboardInterrupt:
            sys.exit(1)