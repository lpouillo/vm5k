#!/usr/bin/ruby

list_of_threads = []
`virsh list | tail -n+3 | grep -v "^$" | awk '{print $2 }'`.each_line { |line|

	vm_name = line.strip
	thread = Thread.new {
		cmd = "ssh -o LogLevel=quiet -o StrictHostKeyChecking=no #{vm_name} \"top -b -n 2 | grep 'Cpu(s):' | sed 's/[^0-9.,]*//g' | sed 's/,/ /g' | tail -n 1\""
                consumptions = `#{cmd}`
		
                puts "#{vm_name} #{consumptions}"
	}

	thread.run

	list_of_threads = list_of_threads.insert(0, thread)

}

list_of_threads.each { |thread|
	thread.join()
}
