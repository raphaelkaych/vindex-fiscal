from django.core.paginator import Paginator

SIZES=(10,15,20,25,50,100)


def paginate(request,objects,default=20,param='page',size_param='per_page'):
    try:size=int(request.GET.get(size_param,default))
    except (ValueError,TypeError):size=default
    if size not in SIZES:size=default
    page=Paginator(objects,size).get_page(request.GET.get(param))
    def url(number):
        query=request.GET.copy();query[param]=number;query[size_param]=size
        return '?'+query.urlencode()
    page.first_url=url(1);page.last_url=url(page.paginator.num_pages)
    page.previous_url=url(page.previous_page_number()) if page.has_previous() else ''
    page.next_url=url(page.next_page_number()) if page.has_next() else ''
    page.navigation_links=[{'number':n,'url':url(n),'current':n==page.number} for n in range(max(1,page.number-2),min(page.paginator.num_pages,page.number+2)+1)]
    page.size_choices=SIZES;page.size_param=size_param
    page.query_fields=[(key,value) for key,values in request.GET.lists() if key not in {param,size_param} for value in values]
    return page
