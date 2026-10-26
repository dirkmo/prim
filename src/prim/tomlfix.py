def workaround(l):
    # toml lib has a bug
    # when loading a file with a list containing an string element "," it is replaced by two empty string elements
    nl = []
    i = 0
    while i < len(l):
        if (i < len(l)-1) and (l[i] == "") and (l[i+1] == ""):
            nl.append(",")
            i += 1
        else:
            nl.append(l[i])
        i += 1
    return nl
