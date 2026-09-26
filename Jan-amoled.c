#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>

int main(int argc, char *argv[]) {
    char **args = malloc(sizeof(char *) * (size_t)(argc + 3));
    if (!args) {
        perror("malloc");
        return 1;
    }
    args[0] = "python3";
    args[1] = "/usr/lib/jan-amoled/jan-amoled-patch.py";
    for (int i = 1; i < argc; i++)
        args[i + 1] = argv[i];
    args[argc + 1] = NULL;

    execvp("python3", args);
    perror("python3");
    return 1;
}
