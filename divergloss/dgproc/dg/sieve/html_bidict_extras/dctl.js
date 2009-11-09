// Functions to control display of dictionary entries.

// Show or hide the division with given identifier,
// changing the toggle-text that was clicked on correspondingly.
function show_hide (el, id)
{
    cel = el.childNodes[0];
    if (document.getElementById(id).style.display == "none") {
        document.getElementById(id).style.display = "";
        cel.nodeValue = "[-]";
    } else {
        document.getElementById(id).style.display = "none";
        cel.nodeValue = "[+]";
    }

    // Do not follow the link.
    return false;
}
