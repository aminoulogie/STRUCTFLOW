"""Launch GCStructFlow. Robot is connected only when the user presses Connect."""
import argparse
from gcrobot.ui import App

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--project-id',default=None)
    parser.add_argument('--tab',choices=['Levels','Grids','Properties','Draw','Checks'],default='Levels')
    args=parser.parse_args()
    App(args.project_id,args.tab).mainloop()

if __name__=='__main__': main()
