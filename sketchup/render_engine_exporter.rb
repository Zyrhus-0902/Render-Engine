# Render Engine exporter - SketchUp extension loader.
#
# Install: copy this file and the render_engine_exporter/ folder into your
# SketchUp Plugins folder (Window > Extension Manager > Install Extension also
# works if you zip both into a .rbz), then restart SketchUp.

require 'sketchup.rb'
require 'extensions.rb'

module RenderEngine
  module Exporter
    unless file_loaded?(__FILE__)
      ex = SketchupExtension.new('Render Engine Exporter', 'render_engine_exporter/main')
      ex.description = 'Exports the model, scene cameras, sun and materials for the Render Engine pipeline.'
      ex.version     = '0.1.0'
      ex.creator     = 'Render Engine'
      Sketchup.register_extension(ex, true)
      file_loaded(__FILE__)
    end
  end
end
