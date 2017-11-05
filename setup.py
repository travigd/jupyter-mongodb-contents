#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import sys
import setuptools
from setuptools import setup

assert sys.version_info >= (3, 5)

readme_file = open("README.md", 'r')
try:
    detailed_description = readme_file.read()
finally:
    readme_file.close()

setup(
    name='jupyter-mongodb-contents',
    version='0.0.0.0',
    description=("MongoDB backed ContentsManager for Jupyter."),
    long_description=detailed_description,
    url='http://none.yet/',
    author='Travis G. DePrato',
    author_email='travigd@umich.edu',
    license='Apache License 2.0',
    packages=setuptools.find_packages('.'),
    package_dir={'': '.'},

    # this tells setuptools to automatically include any data files it finds
    # inside your package directories that are specified by your MANIFEST.in
    include_package_data=True,

    install_requires=[
      'notebook',
      'nbformat',
      'pymongo',
      'schematics',
      'traitlets',
      'requests'
    ],
    zip_safe=False,
    classifiers=[
      'Intended Audience :: End Users/Desktop'
    ],

)   
