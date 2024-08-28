from flask import Response, request
from flask_restful import Resource
from werkzeug.exceptions import NotFound

import services
from controllers.files import api
from libs.exception import BaseHTTPException
from services.account_service import TenantService
from services.file_service import FileService

from collections import OrderedDict
import pymupdf
import threading
import multiprocessing
class LimitedDict(OrderedDict):
    def __init__(self, limit, *args, **kwargs):
        self.limit = limit
        super().__init__(*args, **kwargs)

    def __setitem__(self, key, value):

        if len(self) >= self.limit:
            self.popitem(last=False)
        # Call the parent class's __setitem__ to insert the item
        super().__setitem__(key, value)

image_preview_cache = LimitedDict(limit=5000)
pdf_cache = LimitedDict(limit=100)

class ImagePreviewApi(Resource):
    def get(self, file_id):
        file_id = str(file_id)

        timestamp = request.args.get('timestamp')
        nonce = request.args.get('nonce')
        sign = request.args.get('sign')

        if not timestamp or not nonce or not sign:
            return {'content': 'Invalid request.'}, 400

        try:
            generator, mimetype = FileService.get_image_preview(
                file_id,
                timestamp,
                nonce,
                sign
            )
        except services.errors.file.UnsupportedFileTypeError:
            raise UnsupportedFileTypeError()

        return Response(generator, mimetype=mimetype)
    
class filePreviewApi(Resource):
    def get(self, file_id):
        file_id = str(file_id)
        # Check if the PDF binary is already in the cache
        if file_id in pdf_cache:
            generator,mimetype = pdf_cache[file_id]
        else:
            # Retrieve the file data and cache it
            try:
                generator, mimetype = FileService.get_file_preview_full(file_id, stream=False)
            except services.errors.file.UnsupportedFileTypeError:
                raise UnsupportedFileTypeError()
            pdf_cache[file_id] = (generator,mimetype)

        # Function to cache all pages as images
        def cache_all_pages(file_id, pdf_binary, shared_cache):
            # Each process will independently open the PDF from the binary data
            doc = pymupdf.Document(stream=pdf_binary)
            for i in range(len(doc)):
                image_key = f"{file_id}-{i + 1}"
                if image_key not in shared_cache:
                    img = doc[i].get_pixmap(dpi=200).pil_tobytes("PNG")
                    shared_cache[image_key] = img

        # Start the background process to cache all pages as images
        cache_process = multiprocessing.Process(
            target=cache_all_pages,
            args=(file_id, generator, image_preview_cache)
        )
        cache_process.start()

        # Return the PDF binary as the response
        return Response(generator, mimetype=mimetype)

class fileImagePreviewApi(Resource):
    def get(self, file_id):
        file_id = str(file_id)
        page = int(request.args.get('page'))
        
        image_key=f"{file_id}-{page}"
        # Check if the page is already in the cache
        if image_key in image_preview_cache:
            return Response(image_preview_cache[image_key], mimetype='image/png')
        
        if file_id in pdf_cache:
           generator,mimetype=pdf_cache[file_id]
        else:
            try:
                generator, mimetype = FileService.get_file_preview_full(file_id, stream=False)
            except services.errors.file.UnsupportedFileTypeError:
                raise UnsupportedFileTypeError()
            pdf_cache[file_id]=(generator,mimetype)
        doc=pymupdf.Document(stream=generator)
        image_preview_cache[image_key] = doc[page-1].get_pixmap(dpi=200).pil_tobytes("PNG")
        response = Response(image_preview_cache[image_key], mimetype='image/png')
        return response

class WorkspaceWebappLogoApi(Resource):
    def get(self, workspace_id):
        workspace_id = str(workspace_id)

        custom_config = TenantService.get_custom_config(workspace_id)
        webapp_logo_file_id = custom_config.get('replace_webapp_logo') if custom_config is not None else None

        if not webapp_logo_file_id:
            raise NotFound('webapp logo is not found')

        try:
            generator, mimetype = FileService.get_public_image_preview(
                webapp_logo_file_id,
            )
        except services.errors.file.UnsupportedFileTypeError:
            raise UnsupportedFileTypeError()

        return Response(generator, mimetype=mimetype)


api.add_resource(ImagePreviewApi, '/files/<uuid:file_id>/image-preview')
api.add_resource(filePreviewApi, '/files/<string:file_id>/file-preview')
api.add_resource(fileImagePreviewApi, '/files/<string:file_id>/file-image-preview')
api.add_resource(WorkspaceWebappLogoApi, '/files/workspaces/<uuid:workspace_id>/webapp-logo')


class UnsupportedFileTypeError(BaseHTTPException):
    error_code = 'unsupported_file_type'
    description = "File type not allowed."
    code = 415
