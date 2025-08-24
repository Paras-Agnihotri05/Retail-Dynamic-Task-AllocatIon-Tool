#!/bin/bash
pkill -f "dist/app"
sleep 1
/Users/parasagnihotri/Desktop/Retail\ Priority\ Task\ Allocator/dist/app &
sleep 2
open http://127.0.0.1:5000