# https://stackoverflow.com/questions/71967887/gtkwave-tcl-script-for-adding-specific-signals

proc listFromFile {filename} {
    set f [open $filename r]
    set data [split [string trim [read $f]]]
    close $f
    return $data
}

set sig_list [listFromFile [file join [file dirname [info script]] signals.txt]]

gtkwave::addSignalsFromList $sig_list
