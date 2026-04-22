from django.http import JsonResponse
from django.core.exceptions import ObjectDoesNotExist
from django.http import Http404
from rest_framework import status
from rest_framework.exceptions import APIException


# Middleware for handling JSON error responses
class JsonErrorResponseMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Get the response from the view function
        response = self.get_response(request)
        return response

    def process_exception(self, request, exception):
        # Convert common exceptions to correct HTTP codes instead of always 500.
        if isinstance(exception, Http404):
            return JsonResponse({"detail": "Не найдено."}, status=status.HTTP_404_NOT_FOUND)

        if isinstance(exception, ObjectDoesNotExist):
            return JsonResponse({"detail": "Не найдено."}, status=status.HTTP_404_NOT_FOUND)

        if isinstance(exception, APIException):
            detail = getattr(exception, "detail", None)
            return JsonResponse({"detail": detail if detail is not None else "Ошибка запроса."}, status=exception.status_code)

        # Fallback
        return JsonResponse({"detail": "Внутренняя ошибка сервера."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# Middleware for handling custom 404 responses
class Custom404Middleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Get the response from the view function
        response = self.get_response(request)
        
        # Only handle 404 for non-API requests
        if not request.path.startswith('/api/'):
            if response is None:
                # If response is None, handle 404 error
                return self.handle_404(request)

            if response.status_code == status.HTTP_404_NOT_FOUND:
                # If response status is 404, handle 404 error
                return self.handle_404(request)

        return response

    def handle_404(self, request):
        # Handle 404 error and return JSON response
        data = {"detail": "Страница не найдена."}
        return JsonResponse(data, status=status.HTTP_404_NOT_FOUND)

