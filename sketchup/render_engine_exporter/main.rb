# Render Engine exporter.
#
# Extensions > Render Engine >
#   Lock scenes to render frame   - give every scene the render aspect ratio (3:2)
#                                   so you compose inside the same frame you render
#   Check scenes                  - list naming / setup problems before exporting
#   Export for rendering...       - write <project>/export/
#
# Output (into the chosen project's export/ folder):
#   model.fbx            the geometry, in metres
#   scenes.json          one camera per scene + sun/shadow settings
#   materials.json       every material used, by name
#   reference/<scene>.png  SketchUp's own view of each scene, for alignment QA

require 'json'
require 'time'
require 'fileutils'

module RenderEngine
  module Exporter
    VERSION = '0.1.0'.freeze
    RENDER_ASPECT = 1.5 # must match render_presets.resolution in config/defaults.yaml
    REFERENCE_WIDTH = 1500
    VIEW_TYPES = %w[EXT INT AER DET ELV].freeze
    SCENE_NAME = /\A(#{VIEW_TYPES.join('|')})-\S+/.freeze

    module_function

    def model
      Sketchup.active_model
    end

    def to_m(point)
      point.to_a.map { |v| v.to_f.to_m.round(5) }
    end

    def without_transitions
      opts = model.options['PageOptions']
      old = opts['ShowTransition']
      opts['ShowTransition'] = false
      yield
    ensure
      opts['ShowTransition'] = old
    end

    def lock_render_frame
      pages = model.pages
      return UI.messagebox('This model has no scenes. Create one scene per render view first.') if pages.count.zero?

      original = pages.selected_page
      model.start_operation('Lock scenes to render frame', true)
      without_transitions do
        pages.each do |page|
          pages.selected_page = page
          model.active_view.camera.aspect_ratio = RENDER_ASPECT
          page.update(1) # PAGE_USE_CAMERA
        end
        pages.selected_page = original if original
      end
      model.commit_operation
      UI.messagebox("#{pages.count} scene(s) now use the #{RENDER_ASPECT}:1 render frame.")
    end

    def scene_problems
      problems = []
      problems << 'No scenes. Create one scene per render view.' if model.pages.count.zero?
      model.pages.each do |page|
        problems << "\"#{page.name}\": name should start with #{VIEW_TYPES.join('/')}- (e.g. EXT-01 Entrance)" unless page.name =~ SCENE_NAME
        problems << "\"#{page.name}\": scene does not save a camera position" unless page.use_camera?
        cam = page.camera
        if cam.aspect_ratio.to_f.zero? || (cam.aspect_ratio - RENDER_ASPECT).abs > 0.01
          problems << "\"#{page.name}\": not locked to the render frame (run 'Lock scenes to render frame')"
        end
      end
      unused = model.materials.select { |m| m.name =~ /\A\[?Color_|\A\[?Material\d*\]?\z/ }
      unused.each { |m| problems << "material \"#{m.name}\" is a SketchUp default name; rename it to a library id" }
      problems
    end

    def check_scenes
      problems = scene_problems
      if problems.empty?
        UI.messagebox('All scenes look ready for rendering.')
      else
        UI.messagebox("Found #{problems.size} issue(s):\n\n" + problems.first(25).join("\n"))
      end
    end

    def camera_hash(cam)
      {
        eye: to_m(cam.eye),
        target: to_m(cam.target),
        up: cam.up.to_a.map { |v| v.round(6) },
        perspective: cam.perspective?,
        fov_deg: cam.perspective? ? cam.fov.round(5) : nil,
        fov_is_height: cam.respond_to?(:fov_is_height?) ? cam.fov_is_height? : true,
        aspect_ratio: cam.aspect_ratio.to_f,
        ortho_height_m: cam.perspective? ? nil : cam.height.to_f.to_m.round(5),
        two_point: cam.respond_to?(:is_2d?) ? cam.is_2d? : false
      }
    end

    def shadow_hash
      si = model.shadow_info
      sun = si['SunDirection']
      {
        latitude: si['Latitude'],
        longitude: si['Longitude'],
        north_angle_deg: si['NorthAngle'].to_f,
        shadow_time: si['ShadowTime'].respond_to?(:iso8601) ? si['ShadowTime'].iso8601 : si['ShadowTime'].to_s,
        tz_offset: si['TZOffset'],
        display_shadows: si['DisplayShadows'],
        sun_direction: sun ? sun.to_a.map { |v| v.round(6) } : nil
      }
    end

    def material_list
      model.materials.map do |m|
        tex = m.texture
        {
          name: m.name,
          display_name: m.display_name,
          color: m.color.to_a.first(3),
          alpha: m.alpha,
          texture: tex ? File.basename(tex.filename.to_s) : nil,
          texture_size_m: tex ? [tex.width.to_f.to_m.round(4), tex.height.to_f.to_m.round(4)] : nil
        }
      end
    end

    def safe_name(name)
      name.gsub(/[^0-9A-Za-z\-_]+/, '_').gsub(/\A_+|_+\z/, '')
    end

    def export_model(dir)
      path = File.join(dir, 'model.fbx')
      options = {
        units: 'm',
        triangulated_faces: true,
        doublesided_faces: false,
        edges: false,
        texture_maps: true,
        separate_disconnected_faces: false,
        swap_yz: false,
        show_summary: false
      }
      return path if model.export(path, options)

      # Fallback for SketchUp versions without FBX export.
      path = File.join(dir, 'model.obj')
      model.export(path, options) ? path : nil
    end

    def export_for_rendering
      return UI.messagebox('This model has no scenes. Create one scene per render view first.') if model.pages.count.zero?

      problems = scene_problems
      unless problems.empty?
        msg = "#{problems.size} issue(s) found:\n\n#{problems.first(15).join("\n")}\n\nExport anyway?"
        return unless UI.messagebox(msg, MB_YESNO) == IDYES
      end

      project = UI.select_directory(title: 'Select the project folder (contains project.yaml)')
      return unless project

      dir = File.join(project, 'export')
      ref_dir = File.join(dir, 'reference')
      FileUtils.mkdir_p(ref_dir)

      Sketchup.status_text = 'Render Engine: exporting geometry...'
      model_path = export_model(dir)
      return UI.messagebox('Model export failed (FBX/OBJ export needs SketchUp Pro).') unless model_path

      view = model.active_view
      pages = model.pages
      original_page = pages.selected_page
      original_camera = Sketchup::Camera.new(view.camera.eye, view.camera.target, view.camera.up)
      scenes = []

      without_transitions do
        pages.each_with_index do |page, i|
          Sketchup.status_text = "Render Engine: scene #{i + 1}/#{pages.count} #{page.name}"
          pages.selected_page = page # applies the scene's style, tags and camera
          cam = view.camera
          cam.aspect_ratio = RENDER_ASPECT if cam.aspect_ratio.to_f.zero?
          ref_name = "reference/#{safe_name(page.name)}.png"
          view.write_image(
            filename: File.join(dir, ref_name),
            width: REFERENCE_WIDTH,
            height: (REFERENCE_WIDTH / RENDER_ASPECT).round,
            antialias: true,
            transparent: false
          )
          scenes << {
            name: page.name,
            description: page.description,
            camera: camera_hash(cam),
            reference_image: ref_name
          }
        end
        pages.selected_page = original_page if original_page
      end
      view.camera = original_camera unless original_page

      data = {
        exporter_version: VERSION,
        sketchup_version: Sketchup.version,
        model_name: model.title,
        model_path: model.path,
        exported_at: Time.now.iso8601,
        model_file: File.basename(model_path),
        model_scale: 1.0,
        up_axis: 'Z',
        units: 'm',
        viewport: { width: view.vpwidth, height: view.vpheight },
        shadow_info: shadow_hash,
        scenes: scenes
      }
      File.write(File.join(dir, 'scenes.json'), JSON.pretty_generate(data))
      File.write(File.join(dir, 'materials.json'), JSON.pretty_generate(material_list))
      Sketchup.status_text = ''
      UI.messagebox("Exported #{scenes.size} scene(s) and #{model.materials.count} material(s) to\n#{dir}")
    end

    unless file_loaded?(__FILE__)
      menu = UI.menu('Extensions').add_submenu('Render Engine')
      menu.add_item('Lock scenes to render frame') { lock_render_frame }
      menu.add_item('Check scenes') { check_scenes }
      menu.add_separator
      menu.add_item('Export for rendering...') { export_for_rendering }
      file_loaded(__FILE__)
    end
  end
end
